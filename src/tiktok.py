"""TikTok Content Posting API publisher (Inbox / draft-mode).

For unaudited apps, TikTok only allows posting to the user's INBOX (drafts).
The user opens the TikTok app, finds the draft in their inbox, taps Post.
That's our default.

If your app gets approved for direct-publishing, set
TIKTOK_DIRECT_PUBLISH=true and the publisher will switch to that flow.

Auth: TikTok access tokens last only 24 hours. To make this work daily we
store the long-lived refresh_token + client credentials as secrets. Before
each publish we exchange them for a fresh access_token, used only for that
run. Refresh tokens last ~365 days; we refresh ours via OAuth once a year.

Two-step upload:
  1) POST /v2/post/publish/inbox/video/init/  -> gets upload_url + publish_id
  2) PUT  upload_url with the mp4 bytes (multipart range upload)
  3) [optional] poll /v2/post/publish/status/fetch/ for FINISHED state

Docs: https://developers.tiktok.com/doc/content-posting-api-reference-upload-video
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

API_BASE = "https://open.tiktokapis.com"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INBOX_INIT = "/v2/post/publish/inbox/video/init/"
DIRECT_INIT = "/v2/post/publish/video/init/"
STATUS = "/v2/post/publish/status/fetch/"

POLL_INTERVAL_S = 4
POLL_TIMEOUT_S = 240


class TikTokError(RuntimeError):
    pass


def refresh_access_token(client_key: str, client_secret: str,
                         refresh_token: str) -> dict:
    """Exchange a refresh_token for a fresh access_token.

    Returns the full token payload. The access_token is good for ~24h.
    The refresh_token returned MAY be the same or rotated; we don't
    persist it back to GitHub by default (it's still valid for ~1 year).
    """
    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    body = _safe_json(r)
    if r.status_code >= 400 or "access_token" not in body:
        raise TikTokError(f"refresh token exchange failed: {body}")
    return body


def _resolve_token() -> str:
    """Get a usable access token: refresh from refresh_token if creds present,
    else fall back to a manually-set TIKTOK_ACCESS_TOKEN."""
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    refresh_token = os.environ.get("TIKTOK_REFRESH_TOKEN", "")

    if client_key and client_secret and refresh_token:
        log.info("Refreshing TikTok access token via refresh_token...")
        body = refresh_access_token(client_key, client_secret, refresh_token)
        token = body["access_token"]
        log.info("Got fresh access_token (expires_in=%s)",
                 body.get("expires_in"))
        return token

    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        raise TikTokError(
            "No TikTok credentials. Set either "
            "(TIKTOK_CLIENT_KEY + TIKTOK_CLIENT_SECRET + TIKTOK_REFRESH_TOKEN) "
            "for auto-refresh, or TIKTOK_ACCESS_TOKEN as a manual fallback."
        )
    log.warning(
        "Using static TIKTOK_ACCESS_TOKEN (expires in 24h). For auto-refresh "
        "set TIKTOK_CLIENT_KEY/SECRET + TIKTOK_REFRESH_TOKEN as well."
    )
    return token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _init_upload(token: str, video_size: int, *, direct: bool,
                 caption: str | None) -> dict:
    """Step 1: tell TikTok we're about to upload, get an upload URL."""
    path = DIRECT_INIT if direct else INBOX_INIT
    payload = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }
    if direct and caption is not None:
        payload["post_info"] = {
            "title": caption[:2000],
            "privacy_level": "SELF_ONLY",  # safe default; user changes in app
            "disable_comment": False,
            "disable_duet": False,
            "disable_stitch": False,
        }

    url = f"{API_BASE}{path}"
    r = requests.post(url, headers=_headers(token), json=payload, timeout=30)
    body = _safe_json(r)
    if r.status_code >= 400 or _err_code(body) != "ok":
        raise TikTokError(f"init upload failed [{r.status_code}]: {body}")
    return body["data"]


def _safe_json(r: requests.Response) -> dict:
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}


def _err_code(body: dict) -> str:
    err = body.get("error") or {}
    return err.get("code", "ok")


def _upload_bytes(upload_url: str, video_path: Path) -> None:
    """Step 2: PUT the video bytes to the upload URL."""
    size = video_path.stat().st_size
    with open(video_path, "rb") as fh:
        headers = {
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        }
        r = requests.put(upload_url, headers=headers, data=fh, timeout=300)
    if r.status_code >= 400:
        raise TikTokError(f"upload PUT failed [{r.status_code}]: {r.text[:500]}")
    log.info("Upload PUT ok (%s, %d bytes)", r.status_code, size)


def _poll_status(token: str, publish_id: str) -> dict:
    """Step 3: poll until processing is finished or errors out."""
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while True:
        r = requests.post(
            f"{API_BASE}{STATUS}",
            headers=_headers(token),
            json={"publish_id": publish_id},
            timeout=30,
        )
        body = _safe_json(r)
        if r.status_code >= 400 or _err_code(body) != "ok":
            raise TikTokError(f"status poll failed [{r.status_code}]: {body}")
        status = body.get("data", {}).get("status")
        log.info("publish_id=%s status=%s", publish_id, status)
        if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            return body["data"]
        if status in ("FAILED", "EXPIRED"):
            raise TikTokError(f"publish failed: {body}")
        if time.monotonic() > deadline:
            raise TikTokError(f"publish polling timed out: {body}")
        time.sleep(POLL_INTERVAL_S)


def publish(video_path: Path, caption: str | None = None,
            token: Optional[str] = None) -> dict:
    """Upload a video to TikTok. Returns the final status payload."""
    token = token or _resolve_token()
    direct = os.environ.get("TIKTOK_DIRECT_PUBLISH", "false").lower() == "true"

    size = video_path.stat().st_size
    log.info("Initializing %s upload (%d bytes)",
             "DIRECT" if direct else "INBOX", size)
    init_data = _init_upload(token, size, direct=direct, caption=caption)
    publish_id = init_data["publish_id"]
    upload_url = init_data["upload_url"]
    log.info("Got publish_id=%s", publish_id)

    _upload_bytes(upload_url, video_path)
    return _poll_status(token, publish_id)
