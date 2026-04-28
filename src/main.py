"""End-to-end entrypoint for local / single-shot runs.

For CI we use src.pipeline_generate then src.pipeline_publish so that the
generated image can be committed to the repo (giving it a public raw URL)
between the two stages. Locally, this `main.py` runs both back-to-back.

Flow:
  load .env -> pick niche -> generate post -> generate image
  -> publish to Instagram (unless DRY_RUN) -> append to posted_log.json
"""
from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from src.pipeline_generate import generate_stage
from src.pipeline_publish import publish_stage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")


def run() -> dict:
    load_dotenv()
    pending = generate_stage()
    return publish_stage(pending)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("Run failed")
        sys.exit(1)
