"""Stage 2: upload today's video to TikTok (drafts inbox).

Reads pending_post.json (written by stage 1 + committed by the GH Action),
uploads the mp4 to TikTok via the Content Posting API, then logs the
result to posted_log.json.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.tiktok import publish

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "posted_log.json"
PENDING_PATH = REPO_ROOT / "pending_post.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("pipeline.publish")


def _read_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        return json.loads(LOG_PATH.read_text())
    except json.JSONDecodeError:
        return []


def _write_log(entries: list[dict]) -> None:
    LOG_PATH.write_text(json.dumps(entries, indent=2))


def publish_stage(pending: dict | None = None) -> dict:
    if pending is None:
        if not PENDING_PATH.exists():
            raise FileNotFoundError("pending_post.json not found — did stage 1 run?")
        pending = json.loads(PENDING_PATH.read_text())

    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    entry = dict(pending)

    if dry_run:
        log.info("DRY_RUN=true, skipping TikTok publish")
        entry["published"] = False
        entry["dry_run"] = True
    else:
        video_path = REPO_ROOT / pending["video_path"]
        if not video_path.exists():
            raise FileNotFoundError(f"video missing: {video_path}")
        try:
            result = publish(video_path, caption=pending.get("full_caption"))
            entry["published"] = True
            entry["tiktok_publish_id"] = result.get("publish_id")
            entry["tiktok_status"] = result.get("status")
        except Exception as e:  # noqa: BLE001
            log.exception("Publish failed")
            entry["published"] = False
            entry["error"] = str(e)
            entries = _read_log()
            entries.append(entry)
            _write_log(entries)
            raise

    entries = _read_log()
    entries.append(entry)
    _write_log(entries)
    if PENDING_PATH.exists():
        try:
            PENDING_PATH.unlink()
        except OSError as e:
            log.warning("Could not delete %s: %s", PENDING_PATH, e)
    log.info(
        "Done. niche=%s bucket=%s published=%s",
        entry.get("niche"),
        entry.get("bucket"),
        entry.get("published"),
    )
    return entry


if __name__ == "__main__":
    load_dotenv()
    try:
        publish_stage()
    except Exception:
        log.exception("Publish stage failed")
        sys.exit(1)
