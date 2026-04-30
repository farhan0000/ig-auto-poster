"""Video composition with ffmpeg.

Takes a 9:16 portrait image + voiceover mp3 + hook + script,
produces a 1080x1920 mp4 ready for TikTok upload:

  - background = the AI image, scaled+cropped to 1080x1920
  - subtle Ken-Burns slow zoom (looks alive, not static)
  - voiceover plays full duration, video length matches voiceover length
  - HOOK: bold, wrapped to 2-3 lines, top third, first 3 seconds
  - SUBTITLES: the script auto-split into 5-7 word chunks, synced to audio
    duration, lower-third placement, bright yellow with thick black stroke
    (TikTok native caption look)
  - OPTIONAL extra OVERLAYS: short punchy phrases that flash in mid-frame at
    key moments — used sparingly so they don't fight with subtitles.
  - small "@thegadgetcity_01" watermark in bottom corner

Requires ffmpeg in PATH (preinstalled on GitHub-hosted ubuntu runners).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import List, Tuple

log = logging.getLogger(__name__)

TARGET_W = 1080
TARGET_H = 1920
FPS = 30
WATERMARK_DEFAULT = "@thegadgetcity_01"

# TikTok native caption look: bright yellow body, thick black stroke.
SUBTITLE_COLOR = "yellow"
SUBTITLE_STROKE = "black@1.0"
HOOK_COLOR = "white"
HOOK_STROKE = "black@1.0"


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
    """ffmpeg drawtext eats certain chars — escape them.

    Newlines need to be escaped specifically to a literal backslash-n in the
    drawtext string so ffmpeg renders them as line breaks.
    """
    return (
        s.replace("\\", "\\\\")
         .replace("\n", "\\\n")  # ffmpeg's drawtext line break
         .replace(":", "\\:")
         .replace("'", "’")  # use a curly apostrophe to avoid quoting hell
         .replace('"', "")
         .replace("%", "\\%")
         .replace(",", "\\,")
    )


def _wrap_text(text: str, max_chars_per_line: int) -> str:
    """Greedy word-wrap. Returns a string with `\n` between lines."""
    return "\n".join(textwrap.wrap(
        text, width=max_chars_per_line,
        break_long_words=False, break_on_hyphens=False,
    )) or text


def _segment_script(script: str, total_duration: float,
                    chunk_words: int = 5) -> List[Tuple[str, float, float]]:
    """Split a script into ~chunk_words-word chunks distributed across duration.

    Returns list of (text, start_s, end_s).
    Approximation: distribute time proportionally to chunk word count.
    """
    # Strip the hook (first sentence) so we don't double-render it.
    # Heuristic: drop the first sentence-end (. ! ?) if the script starts
    # with the hook.
    words = script.split()
    if not words:
        return []

    chunks: List[List[str]] = []
    current: List[str] = []
    for w in words:
        current.append(w)
        # End chunk on natural break (punctuation) OR after chunk_words words.
        if len(current) >= chunk_words and (
            current[-1].endswith((".", "!", "?", ",", ":", ";"))
            or len(current) >= chunk_words + 2
        ):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)

    # Allocate time per chunk, weighted by word count.
    total_words = sum(len(c) for c in chunks)
    out = []
    cursor = 0.0
    for c in chunks:
        share = len(c) / total_words
        dur = share * total_duration
        out.append((" ".join(c), cursor, cursor + dur))
        cursor += dur
    return out


def compose(
    image_path: Path,
    voiceover_path: Path,
    hook: str,
    overlays: List[str],
    out_path: Path,
    watermark: str | None = None,
    script: str | None = None,
) -> Path:
    """Compose the TikTok video. Returns out_path.

    `script` is the same voiceover text the TTS read — used to drive
    synced subtitles. If omitted, no subtitles are drawn (only the
    short `overlays` list).
    """
    _check_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    duration = _ffprobe_duration(voiceover_path)
    if duration < 3:
        raise VideoComposeError(f"Voiceover is too short ({duration:.1f}s)")
    log.info("Voiceover duration: %.2fs", duration)

    watermark = watermark or WATERMARK_DEFAULT

    # Pick a chunky bold font. Roboto Bold is in fonts-roboto on ubuntu and
    # looks much more 'TikTok' than DejaVu. macOS has Arial Bold / Helvetica.
    font_candidates = [
        # Roboto / DejaVu (Linux)
        "/usr/share/fonts/truetype/roboto/RobotoCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Black.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Black.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        # macOS
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    font = next((f for f in font_candidates if Path(f).exists()), None)
    log.info("Using font: %s", font or "(default)")

    drawtext_clauses = []

    def drawtext(text: str, start: float, end: float, *, y_expr: str,
                 fontsize: int, color: str = "white",
                 stroke: str = "black@1.0", borderw: int = 6,
                 box: bool = False, box_color: str = "black@0.45",
                 box_pad: int = 18) -> str:
        opts = [
            f"text='{_escape_drawtext(text)}'",
            f"fontcolor={color}",
            f"fontsize={fontsize}",
            f"borderw={borderw}",
            f"bordercolor={stroke}",
            f"line_spacing=8",
            f"x=(w-text_w)/2",
            f"y={y_expr}",
            f"enable='between(t,{start:.2f},{end:.2f})'",
        ]
        if box:
            opts.extend([f"box=1", f"boxcolor={box_color}",
                         f"boxborderw={box_pad}"])
        if font:
            opts.insert(0, f"fontfile='{font}'")
        return "drawtext=" + ":".join(opts)

    # ---- HOOK ----
    # Wrap to ~16 chars per line so it never bleeds off-screen at fontsize 86
    # on a 1080-wide frame. 2-3 lines max.
    hook_wrapped = _wrap_text(hook, max_chars_per_line=16)
    hook_lines = hook_wrapped.count("\n") + 1
    # Auto-shrink if hook is long (>3 lines after wrap → reduce font).
    hook_fontsize = 86 if hook_lines <= 2 else (74 if hook_lines == 3 else 64)
    hook_end = min(3.2, duration - 0.1)
    drawtext_clauses.append(
        drawtext(
            hook_wrapped, 0.0, hook_end,
            y_expr="h*0.18", fontsize=hook_fontsize,
            color=HOOK_COLOR, stroke=HOOK_STROKE, borderw=8,
        )
    )

    # ---- SUBTITLES (driven by the script, lower third) ----
    if script:
        subtitle_segments = _segment_script(
            script, total_duration=duration - 0.2, chunk_words=5,
        )
        # Start subtitles after the hook fades.
        sub_offset = hook_end + 0.05
        # Compress segments into the post-hook window.
        post_hook_window = max(1.0, duration - sub_offset - 0.4)
        if subtitle_segments:
            scale = post_hook_window / max(0.001, subtitle_segments[-1][2])
            for text, s, e in subtitle_segments:
                ts = sub_offset + s * scale
                te = sub_offset + e * scale
                # Each subtitle stays on screen until the next one starts.
                # Wrap each chunk to 2 lines max for readability.
                wrapped = _wrap_text(text, max_chars_per_line=22)
                drawtext_clauses.append(
                    drawtext(
                        wrapped, ts, te,
                        y_expr="h*0.72", fontsize=58,
                        color=SUBTITLE_COLOR, stroke=SUBTITLE_STROKE,
                        borderw=7,
                    )
                )

    # ---- EXTRA OVERLAYS (mid-frame, sparse) ----
    # Now that subtitles cover most of the video, overlays become
    # 'punctuation marks' — show 1-2 of them only, in the upper third,
    # so they emphasize key moments without fighting with subtitles.
    if overlays:
        chosen = overlays[:2]
        slot_dur = (duration - hook_end - 1) / max(1, len(chosen))
        for i, ov in enumerate(chosen):
            s = hook_end + 0.5 + i * slot_dur + slot_dur * 0.3
            e = min(duration - 0.5, s + 1.6)
            ov_wrapped = _wrap_text(ov, max_chars_per_line=18)
            drawtext_clauses.append(
                drawtext(
                    ov_wrapped, s, e,
                    y_expr="h*0.42", fontsize=70,
                    color="white", stroke="black@1.0", borderw=8,
                    box=True, box_color="black@0.55", box_pad=22,
                )
            )

    # ---- WATERMARK ----
    drawtext_clauses.append(
        drawtext(
            watermark, 0.0, duration,
            y_expr="h-h*0.04", fontsize=28,
            color="white@0.9", stroke="black@0.9", borderw=3,
        )
    )

    # Background: scale-and-crop to 1080x1920 + Ken Burns slow zoom.
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
