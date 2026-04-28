"""Niche selection + caption/hashtag generation."""
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
class PostPlan:
    niche: str
    angle: str
    hook: str
    caption: str
    hashtags: List[str]
    image_prompt: str

    def to_dict(self) -> dict:
        return {
            "niche": self.niche,
            "angle": self.angle,
            "hook": self.hook,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "image_prompt": self.image_prompt,
        }


def _load_niches() -> dict:
    with open(NICHES_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def pick_niche(history: List[str] | None = None) -> dict:
    """Weighted pick, biased away from the most recently used niche."""
    cfg = _load_niches()
    history = history or []
    last = history[-1] if history else None

    pool = []
    for n in cfg["niches"]:
        weight = n.get("weight", 1)
        if n["name"] == last:  # avoid back-to-back repeats
            weight = max(1, weight // 2)
        pool.extend([n] * weight)

    pick = random.choice(pool)
    return {
        "name": pick["name"],
        "angle_examples": pick.get("angle_examples", []),
        "audience": cfg["audience_countries"],
        "language": cfg["language"],
    }


def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def generate_post(niche: dict, model: str | None = None) -> PostPlan:
    """Ask the model for a structured Instagram post in one call."""
    model = model or os.environ.get("OPENAI_TEXT_MODEL", "gpt-4o-mini")

    audience = ", ".join(niche["audience"])
    examples = "\n".join(f"- {a}" for a in niche["angle_examples"])

    system = (
        "You are an Instagram content strategist. You write for an audience "
        f"in {audience} (English-speaking, high-RPM ad markets). Tone is "
        "informative, punchy, and trustworthy. You never give specific "
        "financial, legal, or medical advice tailored to an individual; you "
        "stick to widely-accepted educational information and always include "
        "a brief 'this is general info, not advice' line where relevant."
    )

    user = f"""Generate a single Instagram post for the niche: **{niche['name']}**.

Pick a fresh, specific angle. Examples of angles in this niche (do not just copy):
{examples}

Return strict JSON with these keys (and ONLY these keys):
{{
  "angle": "1-line description of the specific angle you chose",
  "hook": "first line of the caption — must stop the scroll. <=80 chars.",
  "caption": "full caption including the hook as its first line. 100-160 words. Use short paragraphs and one or two line-breaks. End with a soft call-to-action like 'Save this' or 'Which surprised you?'",
  "hashtags": ["array", "of", "exactly", "20", "hashtags", "without", "the", "#", "symbol", "mixing", "broad", "and", "niche", "tags", "english", "only", "no", "banned", "or", "spammy"],
  "image_prompt": "A vivid, photorealistic prompt for an image generator. No text in the image. Square 1:1 composition. Clean, modern, scroll-stopping. Avoid stock-photo cliches. <=80 words."
}}

The hashtags should be lowercase, no spaces, and relevant to the niche + angle.
Do not include emojis in `hook` or `image_prompt`. A few tasteful emojis in the caption body are fine.
Output ONLY the JSON object, no markdown fence."""

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
    # Hard-cap at 30 (IG limit) and de-dup while preserving order.
    seen, deduped = set(), []
    for h in hashtags:
        if h and h not in seen:
            seen.add(h)
            deduped.append(h)
    hashtags = deduped[:30]

    return PostPlan(
        niche=niche["name"],
        angle=data["angle"],
        hook=data["hook"],
        caption=data["caption"],
        hashtags=hashtags,
        image_prompt=data["image_prompt"],
    )


def render_caption(plan: PostPlan) -> str:
    """Final caption text sent to Instagram (caption + hashtag block)."""
    tag_line = " ".join(f"#{h}" for h in plan.hashtags)
    return f"{plan.caption}\n\n.\n.\n.\n{tag_line}"
