"""Stage 1 of the CI pipeline: pick a niche, write a post, render an image.

Writes the result two places:
  1. pending_post.json + images/<ts>.jpg  — used by the auto-publish stage
     when IG credentials are configured.
  2. posts/<YYYY-MM-DD>/{image.jpg, caption.txt, post.json}  — a clean,
     human-friendly bundle for *manual posting*. Open it on github.com or
     in the local repo, copy the caption, save the image, post in IG.

Either mode uses the same generated content; only stage 2 differs.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.content import generate_post, pick_niche, render_caption
from src.image import generate_image

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "posted_log.json"
PENDING_PATH = REPO_ROOT / "pending_post.json"
POSTS_DIR = REPO_ROOT / "posts"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("pipeline.generate")


def _read_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        return json.loads(LOG_PATH.read_text())
    except json.JSONDecodeError:
        return []


def generate_stage() -> dict:
    history = [e["niche"] for e in _read_log()][-5:]
    niche = pick_niche(history=history)
    log.info("Picked niche: %s", niche["name"])

    plan = generate_post(niche)
    log.info("Angle: %s", plan.angle)
    caption = render_caption(plan)

    image_path = generate_image(plan.image_prompt)

    pending = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "niche": plan.niche,
        "angle": plan.angle,
        "hook": plan.hook,
        "image_path": str(image_path.relative_to(REPO_ROOT)),
        "hashtags": plan.hashtags,
        "caption_body": plan.caption,
        "full_caption": caption,
    }
    PENDING_PATH.write_text(json.dumps(pending, indent=2))
    log.info("Wrote %s", PENDING_PATH.name)

    # Also write a human-friendly bundle for manual posting.
    today_dir = POSTS_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(image_path, today_dir / "image.jpg")
    (today_dir / "caption.txt").write_text(caption)
    (today_dir / "post.json").write_text(json.dumps(pending, indent=2))
    log.info("Wrote manual-posting bundle to %s/", today_dir.relative_to(REPO_ROOT))

    return pending


if __name__ == "__main__":
    load_dotenv()
    try:
        generate_stage()
    except Exception:
        log.exception("Generate stage failed")
        sys.exit(1)
