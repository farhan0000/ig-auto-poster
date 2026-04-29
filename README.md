# ig-auto-poster

Automated daily Instagram poster targeting **high-RPM English-language niches** (US/UK/CA/AU audiences). Each day the workflow:

1. Picks a niche from `config/niches.yaml` (weighted, avoids back-to-back repeats).
2. Asks OpenAI to write an Instagram-ready caption + 20 hashtags + an image prompt.
3. Generates a 1024×1024 image via OpenAI Images.
4. Commits the image to your fork so it has a public `raw.githubusercontent.com` URL.
5. Publishes a single-image feed post via the **official Instagram Graph API**.
6. Logs the result to `posted_log.json`.

No unofficial libraries, no username/password automation, no ToS violations.

---

## Architecture

```
GitHub Actions cron (14:00 UTC daily)
  ├─ pipeline_generate.py
  │    ├─ pick niche (weighted, history-aware)
  │    ├─ OpenAI Chat → caption + hashtags + image_prompt
  │    └─ OpenAI Images → images/<timestamp>.jpg
  │
  ├─ git commit + push   ← so raw.githubusercontent.com serves the image
  │
  └─ pipeline_publish.py
       └─ Graph API: POST /media → poll → POST /media_publish
```

---

## Setup

### 1. Fork this repo to your own GitHub account

The workflow commits images back into the repo, so it must be in your account. A **public** repo is fine (the images are already public on Instagram). A private repo also works because GitHub Actions uses an authenticated `raw` URL via a token — but the simplest path is **public**.

### 2. Get your Instagram credentials

This project uses the **Instagram Login** flow — no Facebook Page required. You only need:

- An Instagram **Business** or **Creator** account (free conversion in IG settings).
- A Meta developer account (signs in with any Facebook account — even a throwaway one).
- A Meta app with the **Instagram → "API setup with Instagram login"** product added.

| Secret | What it is | How to get it |
|---|---|---|
| `IG_USER_ID` | Numeric ID of your IG Business/Creator account | Once you have a token (below), `GET https://graph.instagram.com/v21.0/me?fields=user_id,username&access_token=...` returns it. |
| `IG_ACCESS_TOKEN` | **Long-lived IG user access token** | In your Meta app: Instagram → API setup with Instagram login → "Generate access token". Exchange the short-lived token for a long-lived one at `https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=...&access_token=...`. Returns a 60-day token starting `IGQV...`. |

Long-lived IG tokens last ~60 days. **Set a calendar reminder** to refresh — or hit `GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<current>` before it expires.

### 3. Get your OpenAI API key

[platform.openai.com](https://platform.openai.com/api-keys). The account needs access to `gpt-4o-mini` (cheap, ~$0.001/post for text) and `gpt-image-1` (~$0.04 for a 1024×1024 image). **Total cost ≈ $0.05/day = ~$1.50/month.**

### 4. Set GitHub secrets

In your fork: **Settings → Secrets and variables → Actions → New repository secret**. Add three:

- `OPENAI_API_KEY`
- `IG_USER_ID`
- `IG_ACCESS_TOKEN`

(`GH_RAW_BASE` is computed automatically by the workflow from the repo name.)

### 5. Test it manually before letting the cron fire

Go to **Actions → Daily Instagram Post → Run workflow** and:

1. **First run: tick "dry run"** — generates the image and commits it but does NOT publish. Verify the image looks decent.
2. **Second run: untick dry run** — actually publishes. Check Instagram.

If both succeed, the daily cron at 14:00 UTC takes over from there.

### 6. Tune the schedule

The default schedule rotates the post time across the week to hit a mix of US engagement peaks (mornings, lunch) and conversion peaks (evenings, Sunday night). Each scheduled run also waits a random 0–25 minutes before posting, so the time-of-day drifts within a window rather than landing exactly on the cron tick.

| Day | UTC | US ET | US PT | UK | Why this slot |
|---|---|---|---|---|---|
| Mon | 13:00 | 9:00 am | 6:00 am | 1:00 pm | Morning commute scroll |
| Tue | 16:30 | 12:30 pm | 9:30 am | 5:30 pm | US lunch + UK evening |
| Wed | 12:00 | 8:00 am | 5:00 am | 1:00 pm | Mid-week morning peak |
| Thu | 22:30 | 6:30 pm | 3:30 pm | 11:30 pm | After-work US scroll |
| Fri | 17:30 | 1:30 pm | 10:30 am | 6:30 pm | Friday lunch |
| Sat | 14:00 | 10:00 am | 7:00 am | 3:00 pm | Saturday morning coffee |
| Sun | 23:00 | 7:00 pm | 4:00 pm | 12:00 am | Sunday-night high-conversion window |

To shift everything by an hour (DST changes, etc.), bump every UTC hour up or down by 1 in `.github/workflows/daily-post.yml`. To tighten or loosen the random delay, change `RANDOM % 1500` (1500 = max 25 min). To post twice a day, just add another cron line per day.

---

## Local development

```bash
git clone <your-fork>
cd ig-auto-poster
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env, then:
DRY_RUN=true python -m src.main          # generate only
DRY_RUN=false python -m src.main         # actually publish
```

---

## Tuning content

`config/niches.yaml` controls which niches run and how often. Higher `weight` = more frequently chosen. Add `angle_examples` to steer the model toward angles you like — it picks something fresh, but uses your examples as a style guide.

If you want to **add a niche** (say, fitness), just add a new entry. If you want to **kill a niche**, drop its weight to 0 or remove it.

---

## What happens when something fails

| Failure | What you see | What to do |
|---|---|---|
| OpenAI API down / rate-limited | GH Actions email "workflow failed" | Re-run manually; usually transient |
| Image fails IG validation | Container returns `ERROR` status | Check `posted_log.json` — usually means the image isn't a clean JPEG. Re-run. |
| IG token expired | Graph API 190 error | Refresh the long-lived token (60-day expiry), update the `IG_ACCESS_TOKEN` secret |
| Caption rejected | IG returns invalid_param | Edit `niches.yaml` to soften the angle examples (sometimes finance/medical wording trips filters) |

All errors are written to `posted_log.json` with the full `error` string for forensics.

---

## What this **does not** do (yet)

- Stories, Reels, or carousels (single-image feed posts only)
- Replying to comments / DMs
- Hashtag research from real-time IG search
- A/B testing of hooks
- Image-quality filter (you'll get the occasional weird DALL-E hand)

These are all small additions if you want them — open an issue or just hack on it.

---

## Compliance / ToS notes

- Uses Meta's **official Graph API** (`/media` + `/media_publish`). Allowed.
- Does **not** use instagrapi, instabot, or anything based on the private/mobile API. Those will get your account flagged.
- Does **not** include personalized financial/legal/medical advice in posts (the system prompt forbids it). Keep it that way to stay on the right side of Meta's ad policies even when you eventually boost posts.
