"""Image generation via OpenAI Images API.

Saves to images/<date>.jpg so the GitHub Action can commit it back to the
repo and we can serve it at https://raw.githubusercontent.com/.../images/...
which Meta's Graph API requires (it pulls the image by URL).
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = REPO_ROOT / "images"


def generate_image(prompt: str, model: str | None = None) -> Path:
    """Generate a 1024x1024 image, save as JPEG, return its path."""
    model = model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # gpt-image-1 always returns base64 in `b64_json`.
    resp = client.images.generate(
        model=model,
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    item = resp.data[0]

    if getattr(item, "b64_json", None):
        raw = base64.b64decode(item.b64_json)
    elif getattr(item, "url", None):
        # dall-e-3 fallback path
        import requests
        r = requests.get(item.url, timeout=60)
        r.raise_for_status()
        raw = r.content
    else:
        raise RuntimeError("OpenAI image response had neither b64_json nor url")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_path = IMAGES_DIR / f"{stamp}.jpg"

    # Save as JPEG (IG requires JPEG for Graph API publish).
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(raw)).convert("RGB")
        img.save(out_path, "JPEG", quality=92, optimize=True)
    except ImportError:
        # Pillow not installed — write raw bytes. OpenAI returns PNG by default
        # for gpt-image-1, which IG rejects. We add Pillow to requirements.
        log.warning("Pillow not installed; saving raw bytes (may not be JPEG)")
        out_path.write_bytes(raw)

    log.info("Saved image to %s", out_path)
    return out_path


def public_url_for(image_path: Path) -> str:
    """Build the raw.githubusercontent.com URL for a committed image."""
    base = os.environ.get("GH_RAW_BASE", "").rstrip("/")
    if not base:
        raise RuntimeError(
            "GH_RAW_BASE env var is not set — cannot build public image URL"
        )
    rel = image_path.relative_to(REPO_ROOT).as_posix()
    return f"{base}/{rel}"
