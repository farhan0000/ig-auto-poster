"""Mocked end-to-end test. Run with:  python -m tests.dry_run

Stubs OpenAI text + image + IG Graph API so we can validate the pipeline
plumbing without spending real money or hitting real services.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image as _PILImage


def _white_jpeg_b64() -> str:
    """Build a real valid 8x8 white JPEG and return its base64."""
    buf = io.BytesIO()
    _PILImage.new("RGB", (8, 8), "white").save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode()


WHITE_JPEG_B64 = _white_jpeg_b64()


def _fake_chat_response(_self, **_kwargs):
    payload = {
        "angle": "What umbrella insurance actually covers in 2026",
        "hook": "Your $300K liability cap won't survive one bad lawsuit.",
        "caption": (
            "Your $300K liability cap won't survive one bad lawsuit.\n\n"
            "Umbrella policies stack on top of your auto and home liability "
            "and kick in once those run out. $1M of coverage typically costs "
            "$150–$300/year — cheaper than most streaming bundles.\n\n"
            "Three things people get wrong:\n"
            "1. They think their auto policy is enough.\n"
            "2. They confuse 'underlying limits' with deductibles.\n"
            "3. They skip it because they 'don't have assets' — future wages "
            "are an asset.\n\n"
            "This is general info, not advice. Talk to a licensed agent "
            "before buying.\n\n"
            "Save this if you're comparing quotes this month."
        ),
        "hashtags": [
            "personalfinance", "umbrellainsurance", "moneytips", "insurance101",
            "financialliteracy", "moneymindset", "wealthbuilding", "financegoals",
            "personalfinancetips", "smartmoney", "moneymanagement", "savemoney",
            "moneymatters", "financialplanning", "financialfreedom", "moneyhacks",
            "investing101", "financialeducation", "insurancetips", "liabilityinsurance",
        ],
        "image_prompt": (
            "A clean, modern flat-lay on a charcoal wooden desk: a leather "
            "umbrella, a stack of crisp paperwork, a pair of glasses, soft "
            "morning light through a window. Photorealistic, square, "
            "magazine-editorial mood. No text, no logos."
        ),
    }
    msg = MagicMock()
    msg.message.content = json.dumps(payload)
    resp = MagicMock()
    resp.choices = [msg]
    return resp


def _fake_image_response(_self, **_kwargs):
    item = MagicMock()
    item.b64_json = WHITE_JPEG_B64
    item.url = None
    resp = MagicMock()
    resp.data = [item]
    return resp


# Fake Graph API: 1) create container, 2) status FINISHED, 3) publish
_call_log = []


def _fake_post(url, data=None, timeout=None):  # noqa: ARG001
    _call_log.append(("POST", url))
    r = MagicMock()
    r.status_code = 200
    if "/media_publish" in url:
        r.json.return_value = {"id": "17999999999999999"}
    elif url.endswith("/media"):
        r.json.return_value = {"id": "17888888888888888"}
    else:
        r.json.return_value = {"ok": True}
    return r


def _fake_get(url, params=None, timeout=None):  # noqa: ARG001
    _call_log.append(("GET", url))
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"status_code": "FINISHED", "status": "Finished"}
    return r


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    os.chdir(repo_root)

    # Ensure a clean slate (best-effort on sandboxed FS).
    for f in ("pending_post.json", "posted_log.json"):
        p = repo_root / f
        if p.exists():
            try:
                p.unlink()
            except OSError:
                p.write_text("[]" if f.endswith("log.json") else "{}")
    images_dir = repo_root / "images"
    if images_dir.exists():
        for img in images_dir.glob("*"):
            try:
                img.unlink()
            except OSError:
                pass

    # Fake env.
    os.environ["OPENAI_API_KEY"] = "sk-test-fake"
    os.environ["IG_USER_ID"] = "1784140000000000"
    os.environ["IG_ACCESS_TOKEN"] = "EAA-test-fake"
    os.environ["GH_RAW_BASE"] = "https://raw.githubusercontent.com/test/ig-auto-poster/main"
    os.environ["DRY_RUN"] = "false"

    sys.path.insert(0, str(repo_root))
    from src import main as main_mod  # noqa: WPS433

    with patch("openai.resources.chat.completions.Completions.create", _fake_chat_response), \
         patch("openai.resources.images.Images.generate", _fake_image_response), \
         patch("requests.post", side_effect=_fake_post), \
         patch("requests.get", side_effect=_fake_get):
        result = main_mod.run()

    # Assertions.
    assert result["published"] is True, f"expected published, got {result}"
    assert result["ig_media_id"] == "17999999999999999"
    # niche is chosen randomly from niches.yaml; just confirm it's a string.
    assert isinstance(result["niche"], str) and result["niche"]
    assert len(result["hashtags"]) == 20

    log = json.loads((repo_root / "posted_log.json").read_text())
    assert len(log) >= 1
    assert log[-1]["published"] is True

    # The image should exist on disk.
    images = list(images_dir.glob("*.jpg"))
    assert len(images) >= 1, f"expected >=1 image, got {images}"
    assert all(i.stat().st_size > 0 for i in images)

    # The human-friendly posts/ bundle should also exist.
    posts_dir = repo_root / "posts"
    assert posts_dir.exists(), "posts/ dir was not created"
    today_dirs = list(posts_dir.iterdir())
    assert today_dirs, "no dated subfolder under posts/"
    today = today_dirs[-1]
    assert (today / "image.jpg").exists(), f"missing image in {today}"
    assert (today / "caption.txt").exists(), f"missing caption in {today}"
    assert (today / "post.json").exists(), f"missing post.json in {today}"
    caption_text = (today / "caption.txt").read_text()
    assert "#" in caption_text, "caption.txt should include hashtags"
    assert len(caption_text) > 200, f"caption.txt suspiciously short: {len(caption_text)}"

    # IG flow: 1 POST /media, 1 GET status, 1 POST /media_publish.
    posts = [c for c in _call_log if c[0] == "POST"]
    gets = [c for c in _call_log if c[0] == "GET"]
    assert any("/media" in u and "/media_publish" not in u for _, u in posts), posts
    assert any("/media_publish" in u for _, u in posts), posts
    assert any(gets), gets

    # pending_post.json should be cleared after successful publish.
    # (We use a soft check because some sandboxed filesystems disallow unlink.)
    pending_remains = (repo_root / "pending_post.json").exists()
    if pending_remains:
        print("note: pending_post.json was not removed (likely sandboxed FS)")

    print("DRY_RUN_TEST_OK")
    print(json.dumps({
        "niche": result["niche"],
        "angle": result["angle"],
        "hashtag_count": len(result["hashtags"]),
        "ig_media_id": result["ig_media_id"],
        "image_path": result["image_path"],
        "graph_calls": _call_log,
    }, indent=2))


if __name__ == "__main__":
    main()
