"""Stage 1 of the CI pipeline: pick a niche, write a post, render an image.

Writes everything to pending_post.json so stage 2 can read it after the GH
Action commits the image (giving it a public raw URL).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.content import generate_post, pick_niche, render_caption
from src.image import generate_image

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "posted_log.json"
PENDING_PATH = REPO_ROOT / "pending_post.json"

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
    return pending


if __name__ == "__main__":
    load_dotenv()
    try:
        generate_stage()
    except Exception:
        log.exception("Generate stage failed")
        sys.exit(1)
