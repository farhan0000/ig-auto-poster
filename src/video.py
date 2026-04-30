"""Video composition with ffmpeg.

Takes a 9:16 portrait image + voiceover mp3 + a list of on-screen text
overlays, produces a 1080x1920 mp4 ready for TikTok upload:

  - background = the AI image, scaled+padded to 1080x1920
  - subtle Ken-Burns slow zoom (looks alive, not static)
  - voiceover plays full duration, video length matches voiceover length
  - at evenly-spaced points during the voiceover, text overlays flash on
    screen (white text, black drop-shadow, big bold sans-serif)
  - hook is shown for the full first 3 seconds at the top
  - small "@thegadgetcity_01" watermark in bottom-right

Requires ffmpeg in PATH (preinstalled on GitHub-hosted ubuntu runners,
and `brew install ffmpeg` on macOS for local testing).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920
FPS = 30
WATERMARK_DEFAULT = "@thegadgetcity_01"


class VideoComposeError(RuntimeError):
    pass


def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise VideoComposeError(
            "ffmpeg not found in PATH. Install it: "
            "`brew install ffmpeg` (macOS) or "
            "`sudo apt-get install -y ffmpeg` (Linux). On GitHub Actions "
            "ubuntu-latest runners ffmpeg is preinstalled."
        )


def _ffprobe_duration(path: Path) -> float:
    """Return media duration in seconds via ffprobe."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        text=True,
    )
    return float(json.loads(out)["format"]["duration"])


def _escape_drawtext(s: str) -> str:
    """ffmpeg drawtext eats certain chars — escape them."""
    return (
        s.replace("\\", "\\\\")
         .replace(":", "\\:")
         .replace("'", "’")  # use a curly apostrophe to avoid quoting hell
         .replace('"', "")
         .replace("%", "\\%")
         .replace(",", "\\,")
    )


def compose(
    image_path: Path,
    voiceover_path: Path,
    hook: str,
    overlays: List[str],
    out_path: Path,
    watermark: str | None = None,
) -> Path:
    """Compose the TikTok video. Returns out_path."""
    _check_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    duration = _ffprobe_duration(voiceover_path)
    if duration < 3:
        raise VideoComposeError(f"Voiceover is too short ({duration:.1f}s)")
    log.info("Voiceover duration: %.2fs", duration)

    watermark = watermark or WATERMARK_DEFAULT

    # Find a usable bold font. GH Actions ubuntu has DejaVu; macOS has Arial.
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    font = next((f for f in font_candidates if Path(f).exists()), None)

    # Build drawtext clauses for hook (always visible 0-3s) + overlays
    # (each one shown for ~1.5s, evenly spread across the rest of the video).
    drawtext_clauses = []

    def drawtext(text: str, start: float, end: float, y_expr: str,
                 fontsize: int) -> str:
        opts = [
            f"text='{_escape_drawtext(text)}'",
            f"fontcolor=white",
            f"fontsize={fontsize}",
            f"borderw=4",
            f"bordercolor=black@0.85",
            f"box=1",
            f"boxcolor=black@0.45",
            f"boxborderw=22",
            f"x=(w-text_w)/2",
            f"y={y_expr}",
            f"enable='between(t,{start:.2f},{end:.2f})'",
        ]
        if font:
            opts.insert(0, f"fontfile='{font}'")
        return "drawtext=" + ":".join(opts)

    # Hook — top of frame, big.
    drawtext_clauses.append(
        drawtext(hook, 0.0, min(3.5, duration - 0.1),
                 y_expr="h*0.12", fontsize=58)
    )

    # Overlays evenly spaced across [3, duration-1].
    if overlays:
        window_start = 3.5
        window_end = max(window_start + 1, duration - 1.0)
        slot = (window_end - window_start) / max(1, len(overlays))
        for i, ov in enumerate(overlays):
            s = window_start + i * slot
            e = min(window_end, s + min(2.0, slot * 0.95))
            drawtext_clauses.append(
                drawtext(ov, s, e, y_expr="h*0.78", fontsize=52)
            )

    # Watermark — small, bottom right, always visible.
    drawtext_clauses.append(
        drawtext(watermark, 0.0, duration,
                 y_expr="h-h*0.05", fontsize=30)
    )

    # Background filter chain:
    # 1) scale image keeping aspect, 2) pad/crop to 1080x1920, 3) Ken-Burns
    #    zoom from 1.00 -> 1.08 over the full duration.
    bg_filter = (
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_W}:{TARGET_H},"
        f"zoompan=z='min(zoom+0.0006,1.08)':d={int(duration*FPS)}:s={TARGET_W}x{TARGET_H}:fps={FPS}"
    )
    text_filter = ",".join(drawtext_clauses)
    full_filter = f"{bg_filter},{text_filter}"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(voiceover_path),
        "-vf", full_filter,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]
    log.info("Running ffmpeg (%d filters)", len(drawtext_clauses))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("ffmpeg stderr (tail): %s", proc.stderr[-2000:])
        raise VideoComposeError(f"ffmpeg failed with code {proc.returncode}")

    log.info("Wrote video to %s (%d bytes)", out_path, out_path.stat().st_size)
    return out_path
