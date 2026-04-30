"""Mocked end-to-end test for the TikTok pipeline.

Stubs OpenAI text + image + TTS + TikTok API. Validates that the pipeline
produces a real .mp4 (via real ffmpeg) end-to-end without spending money.

Run:  python -m tests.dry_run
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image as _PILImage


def _portrait_jpeg_b64() -> str:
    """Build a real valid 32x48 portrait JPEG and return its base64."""
    buf = io.BytesIO()
    _PILImage.new("RGB", (32, 48), "lightgray").save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode()


PORTRAIT_JPEG_B64 = _portrait_jpeg_b64()


def _silent_mp3() -> bytes:
    """Make a tiny but valid silent mp3 the voice synth can return.

    Five seconds of silence as an MP3 frame stream. We rely on ffmpeg to be
    tolerant — it just needs *something* it can read as audio. Easiest
    fix: have lame/ffmpeg generate one and embed it. We can't shell out
    here, so we ship a known-good 5s silent MP3 base64.
    """
    # Generate via PIL? No — use ffmpeg if present (we always run in CI/local
    # where ffmpeg exists). Tests already require ffmpeg to validate the
    # video step.
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        out = f.name
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
            "-t", "5", "-c:a", "libmp3lame", "-q:a", "9", out,
        ]
    )
    data = Path(out).read_bytes()
    Path(out).unlink()
    return data


def _fake_chat_response(_self, **_kwargs):
    payload = {
        "angle": "Magnetic charging cables that survive backpack abuse",
        "hook": "Stop replacing frayed charging cables every 3 months.",
        "script": (
            "Stop replacing frayed charging cables every 3 months. Magnetic tip "
            "cables fix this with one trick: the cable disconnects when something "
            "yanks it, so the strain never reaches the wire. You leave the tiny "
            "tip in your phone, and the cable snaps onto it. Fifteen bucks for "
            "a three-pack on Amazon. They charge as fast as the original. "
            "Save this if your last cable died in your backpack."
        ),
        "overlays": [
            "Magnetic tip stays in",
            "Yank-proof",
            "$15 for 3-pack",
            "Saves you cables",
        ],
        "caption": "Why is no one talking about magnetic charging cables 🔌",
        "hashtags": ["techtok", "gadgets", "techhacks", "chargingcable", "gadgetreview"],
        "image_prompt": (
            "A cinematic close-up of a sleek black phone on a wooden desk with "
            "a magnetic USB-C charging tip plugged in, soft warm bokeh in the "
            "background, shallow depth of field, vertical 9:16, photorealistic. "
            "No text, no logos."
        ),
    }
    msg = MagicMock()
    msg.message.content = json.dumps(payload)
    resp = MagicMock()
    resp.choices = [msg]
    return resp


def _fake_image_response(_self, **_kwargs):
    item = MagicMock()
    item.b64_json = PORTRAIT_JPEG_B64
    item.url = None
    resp = MagicMock()
    resp.data = [item]
    return resp


_silent_audio: bytes | None = None


def _fake_tts_response(_self, **_kwargs):
    global _silent_audio
    if _silent_audio is None:
        _silent_audio = _silent_mp3()
    resp = MagicMock()
    resp.content = _silent_audio
    resp.read = lambda: _silent_audio
    return resp


# Fake TikTok API: init -> upload PUT -> status poll
_call_log: list[tuple[str, str]] = []


def _fake_tiktok_post(url, headers=None, json=None, data=None, timeout=None):  # noqa: ARG001
    _call_log.append(("POST", url))
    r = MagicMock()
    r.status_code = 200
    if "/inbox/video/init/" in url or "/post/publish/video/init/" in url:
        r.json.return_value = {
            "data": {
                "publish_id": "v_pub_123",
                "upload_url": "https://upload.tiktokapis.com/upload/abc",
            },
            "error": {"code": "ok", "message": ""},
        }
    elif "/post/publish/status/fetch/" in url:
        r.json.return_value = {
            "data": {"publish_id": "v_pub_123", "status": "SEND_TO_USER_INBOX"},
            "error": {"code": "ok", "message": ""},
        }
    else:
        r.json.return_value = {"error": {"code": "ok"}}
    return r


def _fake_tiktok_put(url, headers=None, data=None, timeout=None):  # noqa: ARG001
    _call_log.append(("PUT", url))
    # Drain the file-like body to mimic a real upload.
    if hasattr(data, "read"):
        _ = data.read()
    r = MagicMock()
    r.status_code = 201
    r.text = ""
    return r


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    # Ensure a clean slate (best-effort).
    for f in ("pending_post.json", "posted_log.json"):
        p = repo_root / f
        if p.exists():
            try:
                p.unlink()
            except OSError:
                p.write_text("[]" if f.endswith("log.json") else "{}")
    posts_dir = repo_root / "posts"
    if posts_dir.exists():
        for sub in posts_dir.iterdir():
            if sub.is_dir():
                try:
                    shutil.rmtree(sub)
                except OSError:
                    pass

    # Fake env. Note: NO TIKTOK_ACCESS_TOKEN to default to dry / generate-only,
    # but we'll explicitly drive both stages to exercise the publish path too.
    os.environ["OPENAI_API_KEY"] = "sk-test-fake"
    os.environ["TIKTOK_ACCESS_TOKEN"] = "tt-test-fake"
    os.environ["DRY_RUN"] = "false"

    sys.path.insert(0, str(repo_root))

    from src.pipeline_generate import generate_stage
    from src.pipeline_publish import publish_stage

    with patch("openai.resources.chat.completions.Completions.create", _fake_chat_response), \
         patch("openai.resources.images.Images.generate", _fake_image_response), \
         patch("openai.resources.audio.speech.Speech.create", _fake_tts_response), \
         patch("requests.post", side_effect=_fake_tiktok_post), \
         patch("requests.put", side_effect=_fake_tiktok_put):
        pending = generate_stage()
        result = publish_stage(pending)

    # Assertions on generation.
    today_dirs = sorted((repo_root / "posts").iterdir())
    assert today_dirs, "no posts/<date>/ created"
    today = today_dirs[-1]
    for f in ("image.jpg", "voiceover.mp3", "video.mp4", "caption.txt", "post.json"):
        assert (today / f).exists(), f"missing {today.name}/{f}"
        assert (today / f).stat().st_size > 0, f"empty {today.name}/{f}"

    # The mp4 should be at least a few KB and parseable as MP4.
    mp4_size = (today / "video.mp4").stat().st_size
    assert mp4_size > 5_000, f"video.mp4 too small ({mp4_size} bytes)"
    with open(today / "video.mp4", "rb") as fh:
        head = fh.read(16)
    # MP4 has 'ftyp' at byte 4
    assert head[4:8] == b"ftyp", f"video.mp4 missing ftyp atom: {head!r}"

    # Caption shape: hashtags inline, count = 5
    caption = (today / "caption.txt").read_text()
    assert caption.count("#") == 5, f"expected 5 hashtags in caption, got {caption.count('#')}"

    # Publish path: should have hit init + put + status
    posts = [c for c in _call_log if c[0] == "POST"]
    puts = [c for c in _call_log if c[0] == "PUT"]
    assert any("/inbox/video/init/" in u for _, u in posts), posts
    assert puts and "upload" in puts[0][1], puts
    assert any("/status/fetch/" in u for _, u in posts), posts

    # Result fields
    assert result["published"] is True, result
    assert result.get("tiktok_publish_id") == "v_pub_123"

    print("DRY_RUN_TEST_OK")
    print(json.dumps({
        "bucket": pending["bucket"],
        "angle": pending["angle"],
        "video_path": pending["video_path"],
        "video_size_kb": round(mp4_size / 1024, 1),
        "publish_id": result.get("tiktok_publish_id"),
        "tiktok_calls": _call_log,
    }, indent=2))


if __name__ == "__main__":
    main()
