"""Stage 1: produce a full daily content bundle.

Outputs into posts/<YYYY-MM-DD>/:
  - image.jpg        (9:16 vertical, used as video background and IG fallback)
  - voiceover.mp3    (TTS of the script)
  - video.mp4        (1080x1920 final TikTok video)
  - caption.txt      (the TikTok caption + hashtags)
  - post.json        (full structured plan)

Also writes pending_post.json at the repo root so stage 2 can find today's
artifact without scanning posts/.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.content import generate_post, pick_bucket, render_caption
from src.image import generate_image
from src.video import compose
from src.voice import synthesize

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
    history = [e.get("bucket", "") for e in _read_log()][-5:]
    bucket = pick_bucket(history=history)
    log.info("Picked bucket: %s (%s)", bucket["bucket"], bucket["niche"])

    plan = generate_post(bucket)
    log.info("Angle: %s", plan.angle)
    log.info("Hook:  %s", plan.hook)
    caption = render_caption(plan)

    today_dir = POSTS_DIR / datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_dir.mkdir(parents=True, exist_ok=True)

    # 1. Image
    raw_image_path = generate_image(plan.image_prompt)
    image_path = today_dir / "image.jpg"
    shutil.copy(raw_image_path, image_path)

    # 2. Voiceover
    voiceover_path = today_dir / "voiceover.mp3"
    synthesize(plan.script, voiceover_path)

    # 3. Video composition
    video_path = today_dir / "video.mp4"
    compose(
        image_path=image_path,
        voiceover_path=voiceover_path,
        hook=plan.hook,
        overlays=plan.overlays,
        script=plan.script,
        out_path=video_path,
    )

    # 4. Caption + post.json
    (today_dir / "caption.txt").write_text(caption)

    pending = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "niche": plan.niche,
        "bucket": plan.bucket,
        "angle": plan.angle,
        "hook": plan.hook,
        "image_path": str(image_path.relative_to(REPO_ROOT)),
        "voiceover_path": str(voiceover_path.relative_to(REPO_ROOT)),
        "video_path": str(video_path.relative_to(REPO_ROOT)),
        "hashtags": plan.hashtags,
        "script": plan.script,
        "overlays": plan.overlays,
        "caption_body": plan.caption,
        "full_caption": caption,
    }
    (today_dir / "post.json").write_text(json.dumps(pending, indent=2))
    PENDING_PATH.write_text(json.dumps(pending, indent=2))

    log.info("Bundle ready at %s/", today_dir.relative_to(REPO_ROOT))
    return pending


if __name__ == "__main__":
    load_dotenv()
    try:
        generate_stage()
    except Exception:
        log.exception("Generate stage failed")
        sys.exit(1)
