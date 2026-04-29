"""Instagram Graph API publisher.

Uses the **Instagram Login** flow (graph.instagram.com), which lets us
publish without needing a Facebook Page or Page access token. The user
authenticates directly via Instagram and we use a long-lived IG user
access token. To switch back to the older FB-Login flow, set
IG_API_BASE=https://graph.facebook.com/v21.0 and use a Page token.

Two-step publish flow per Meta's docs:
  1) POST /{ig-user-id}/media       -> returns a creation_id ("container")
  2) Poll  /{creation_id}?fields=status_code  until FINISHED (or ERROR)
  3) POST /{ig-user-id}/media_publish?creation_id=...

Caption hard-limit per IG: 2,200 chars. Hashtag limit: 30.
We do not retry on permanent errors; we surface them so the GH Action fails
loudly (which sends you the standard workflow-failed email).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

# Default to the Instagram Login API. Override via env if you want the older
# Facebook-Login (Page-based) flow.
DEFAULT_GRAPH = "https://graph.instagram.com/v21.0"
MAX_CAPTION = 2200
POLL_INTERVAL_S = 3
POLL_TIMEOUT_S = 180


def _graph_base() -> str:
    return os.environ.get("IG_API_BASE", DEFAULT_GRAPH).rstrip("/")


class InstagramError(RuntimeError):
    pass


def _post(path: str, params: dict) -> dict:
    url = f"{_graph_base()}/{path}"
    r = requests.post(url, data=params, timeout=60)
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text}
    if r.status_code >= 400 or "error" in body:
        raise InstagramError(f"POST {path} failed [{r.status_code}]: {body}")
    return body


def _get(path: str, params: dict) -> dict:
    url = f"{_graph_base()}/{path}"
    r = requests.get(url, params=params, timeout=60)
    try:
        body = r.json()
    except ValueError:
        body = {"raw": r.text}
    if r.status_code >= 400 or "error" in body:
        raise InstagramError(f"GET {path} failed [{r.status_code}]: {body}")
    return body


def publish(
    image_url: str,
    caption: str,
    ig_user_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Create a single-image media container and publish it.

    Returns the published media object on success.
    """
    ig_user_id = ig_user_id or os.environ["IG_USER_ID"]
    access_token = access_token or os.environ["IG_ACCESS_TOKEN"]

    if len(caption) > MAX_CAPTION:
        log.warning("Caption %d chars > %d limit; truncating", len(caption), MAX_CAPTION)
        caption = caption[: MAX_CAPTION - 1] + "…"

    log.info("Creating IG media container for image %s", image_url)
    container = _post(
        f"{ig_user_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
    )
    creation_id = container["id"]
    log.info("Container created: %s", creation_id)

    # Poll until the container finishes processing.
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while True:
        status = _get(
            creation_id,
            {"fields": "status_code,status", "access_token": access_token},
        )
        code = status.get("status_code")
        log.info("Container %s status: %s", creation_id, code)
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise InstagramError(f"Container errored: {status}")
        if time.monotonic() > deadline:
            raise InstagramError(
                f"Container did not finish in {POLL_TIMEOUT_S}s: {status}"
            )
        time.sleep(POLL_INTERVAL_S)

    log.info("Publishing container %s", creation_id)
    published = _post(
        f"{ig_user_id}/media_publish",
        {"creation_id": creation_id, "access_token": access_token},
    )
    log.info("Published media id: %s", published.get("id"))
    return published
