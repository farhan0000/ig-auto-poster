"""Text-to-speech voiceover via OpenAI's TTS endpoint.

Pipeline:
  script (string) -> mp3 file on disk

OpenAI's tts-1 voices: alloy, echo, fable, onyx, nova, shimmer.
We default to 'onyx' (warm, confident, works for tech/gadgets) but it's
configurable via OPENAI_TTS_VOICE env var.

Cost: ~$0.015 / 1k chars input. A 60-90 word script ~= ~500 chars =>
roughly $0.008 per video.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from openai import OpenAI

log = logging.getLogger(__name__)

DEFAULT_VOICE = "nova"      # friendly, energetic female — best for tech content
DEFAULT_MODEL = "tts-1-hd"  # higher-quality prosody than tts-1, ~2x cost
DEFAULT_FORMAT = "mp3"


def synthesize(script: str, out_path: Path, voice: str | None = None,
               model: str | None = None) -> Path:
    """Generate an mp3 voiceover for `script` and write to `out_path`."""
    voice = voice or os.environ.get("OPENAI_TTS_VOICE", DEFAULT_VOICE)
    model = model or os.environ.get("OPENAI_TTS_MODEL", DEFAULT_MODEL)

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    out_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Synthesizing voiceover (%s, %s, %d chars)",
             model, voice, len(script))

    # The newer SDK exposes streaming via with_streaming_response. We use the
    # simpler non-streaming form for clarity; payloads are small (<1MB).
    resp = client.audio.speech.create(
        model=model,
        voice=voice,
        input=script,
        response_format=DEFAULT_FORMAT,
    )
    # Both `.read()` and `.content` work depending on SDK version.
    audio_bytes = getattr(resp, "content", None)
    if audio_bytes is None and hasattr(resp, "read"):
        audio_bytes = resp.read()
    if audio_bytes is None:
        raise RuntimeError("OpenAI TTS response had no content")

    out_path.write_bytes(audio_bytes)
    log.info("Wrote voiceover to %s (%d bytes)", out_path, len(audio_bytes))
    return out_path
