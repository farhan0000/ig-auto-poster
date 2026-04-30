"""Image generation via OpenAI Images API.

Generates a 9:16 vertical image (1024x1536, the closest to TikTok's
1080x1920 native that gpt-image-1 supports) and saves it as a JPEG.
The video composer scales/crops it to 1080x1920 during ffmpeg compose.
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

# gpt-image-1 supported portrait size closest to 9:16 is 1024x1536.
# We later scale to 1080x1920 in the video composer, which keeps the
# 9:16 aspect ratio without cropping.
DEFAULT_SIZE = "1024x1536"


def generate_image(prompt: str, model: str | None = None, size: str | None = None) -> Path:
    """Generate a 9:16 portrait image, save as JPEG, return its path."""
    model = model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
    size = size or os.environ.get("OPENAI_IMAGE_SIZE", DEFAULT_SIZE)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # gpt-image-1 always returns base64 in `b64_json`.
    resp = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
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
