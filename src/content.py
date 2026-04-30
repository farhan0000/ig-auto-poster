"""Content generation for TikTok (and reusable for IG manual posts).

Single niche (Tech & Gadgets) with rotating angle buckets defined in
config/niches.yaml. Output is a TikTokPlan: a hook, a 15-30s voiceover
script, on-screen text overlays, an image prompt, a caption, and hashtags.
"""
from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml
from openai import OpenAI

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
NICHES_PATH = REPO_ROOT / "config" / "niches.yaml"


@dataclass
class TikTokPlan:
    niche: str
    bucket: str
    angle: str
    hook: str          # the 3-second opening line, also drawn on screen
    script: str        # full voiceover, 15-30s when read aloud (~50-90 words)
    overlays: List[str]  # 2-4 short phrases to flash on screen at key moments
    caption: str       # TikTok caption (short, punchy)
    hashtags: List[str]  # 5 (TikTok performs better with fewer than IG)
    image_prompt: str  # 9:16 vertical image prompt

    def to_dict(self) -> dict:
        return {
            "niche": self.niche,
            "bucket": self.bucket,
            "angle": self.angle,
            "hook": self.hook,
            "script": self.script,
            "overlays": self.overlays,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "image_prompt": self.image_prompt,
        }


def _load_niches() -> dict:
    with open(NICHES_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def pick_bucket(history: List[str] | None = None) -> dict:
    """Weighted pick of an angle bucket, biased away from the most recent."""
    cfg = _load_niches()
    history = history or []
    last = history[-1] if history else None

    pool = []
    for b in cfg["angle_buckets"]:
        weight = b.get("weight", 1)
        if b["bucket"] == last:
            weight = max(1, weight // 2)
        pool.extend([b] * weight)

    pick = random.choice(pool)
    return {
        "niche": cfg["niche"],
        "bucket": pick["bucket"],
        "description": pick["description"],
        "examples": pick.get("examples", []),
        "audience": cfg["audience_countries"],
        "language": cfg["language"],
        "voice": cfg.get("brand", {}).get("voice", ""),
    }


# Backward-compat alias for any code/tests still calling pick_niche.
def pick_niche(history: List[str] | None = None) -> dict:
    return pick_bucket(history)


def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def generate_post(bucket: dict, model: str | None = None) -> TikTokPlan:
    """Ask the model for a structured TikTok video plan in one call."""
    model = model or os.environ.get("OPENAI_TEXT_MODEL", "gpt-4o-mini")

    audience = ", ".join(bucket["audience"])
    examples = "\n".join(f"- {a}" for a in bucket["examples"])

    system = (
        f"You are a TikTok content strategist for a tech & gadgets channel. "
        f"You write for an audience in {audience} (English-speaking). "
        f"Brand voice: {bucket['voice']}. "
        "You produce videos in the 'punchy talking-head' style: 3-second hook, "
        "tight 15-30 second script, 2-4 short on-screen text overlays, no fluff. "
        "Every claim should be true and verifiable; if you're not sure, soften "
        "with 'reportedly' or 'in our testing'. "
        "Avoid medical, financial, or political topics. "
        "Avoid clickbait that doesn't deliver — viewers punish that on TikTok."
    )

    user = f"""Generate ONE TikTok video plan for the angle bucket: **{bucket['bucket']}**.

Bucket description: {bucket['description']}

Example angles in this bucket (do NOT copy verbatim — pick something fresh):
{examples}

Return strict JSON with EXACTLY these keys:
{{
  "angle": "1-line description of the specific angle you chose",
  "hook": "the first line of the video, said in the first 3 seconds. Must stop the scroll. Plain English, <=70 chars. No emojis. Avoid 'POV:' and 'Tell me without telling me' — overused.",
  "script": "the full voiceover script, 50-90 words, written as continuous speech. Includes the hook as its first sentence. Conversational, no list formatting, no headers. End with a single CTA like 'Follow for more', 'Save this', or 'Comment if you've tried it'.",
  "overlays": ["array", "of", "2 to 4", "very short", "phrases", "max 6 words each", "that flash on screen at key moments. Plain text, no emojis."],
  "caption": "TikTok caption, 1-2 sentences max. Casual, often a question or a strong claim. <=150 chars. NO hashtags here — those go in `hashtags`. A single tasteful emoji is fine.",
  "hashtags": ["exactly", "5", "hashtags", "lowercase", "no_hash_symbol"],
  "image_prompt": "A vivid, photorealistic prompt for an image generator. The image will be a 9:16 vertical TikTok background — depict the gadget/topic clearly with cinematic lighting and shallow depth of field. NO text or logos in the image. Avoid stock-photo cliches. <=70 words."
}}

Hashtags rules: 5 only. Mix one big tag (#tech, #gadgets, #techtok), one mid-niche tag (#gadgetreview, #techhacks), and 3 specific to today's topic. Lowercase, no spaces.

Output ONLY the JSON object — no markdown fence, no commentary."""

    resp = _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.9,
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)

    hashtags = [h.lstrip("#").strip().lower() for h in data.get("hashtags", []) if h]
    seen, deduped = set(), []
    for h in hashtags:
        if h and h not in seen:
            seen.add(h)
            deduped.append(h)
    hashtags = deduped[:5]

    overlays = [o.strip() for o in data.get("overlays", []) if o and o.strip()][:4]

    return TikTokPlan(
        niche=bucket["niche"],
        bucket=bucket["bucket"],
        angle=data["angle"],
        hook=data["hook"],
        script=data["script"],
        overlays=overlays,
        caption=data["caption"],
        hashtags=hashtags,
        image_prompt=data["image_prompt"],
    )


def render_caption(plan: TikTokPlan) -> str:
    """Final TikTok caption: caption + space + 5 hashtags inline."""
    tag_line = " ".join(f"#{h}" for h in plan.hashtags)
    return f"{plan.caption} {tag_line}".strip()
