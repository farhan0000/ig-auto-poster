# gadget-city-auto-poster

Automated daily TikTok video generator for **`@thegadgetcity_01`**.

Every day at 05:00 UTC the workflow:

1. Picks a tech/gadget angle bucket (rotating across hidden features, money-saving gadgets, comparisons, etc).
2. Asks OpenAI for a 3-second hook + 60-word script + on-screen overlays + caption + 5 hashtags.
3. Generates a 9:16 vertical image via OpenAI Images.
4. Synthesizes the script into a voiceover (OpenAI TTS).
5. Composites image + voiceover + on-screen text overlays + a slow Ken-Burns zoom into a 1080×1920 TikTok-ready MP4 with `ffmpeg`.
6. Commits the video bundle (`posts/<date>/`) to the repo.
7. *(If `TIKTOK_ACCESS_TOKEN` is set)* uploads the video to your TikTok via the official Content Posting API. With an unaudited app this lands in your **Drafts inbox** — open the TikTok app, tap the draft, tap Post. Once your app is approved for direct-publish, set `TIKTOK_DIRECT_PUBLISH=true` and posts go fully automatic.

No FB account needed. No `instagrapi`. No password automation. Official API only.

---

## Cost

About **$0.05–$0.07 per day** in OpenAI usage (image + TTS + caption text). About **$1.80/month**. GitHub Actions and the TikTok API are free.

## Architecture

```
GitHub Actions cron (05:00 UTC)
  │
  ├─ pipeline_generate.py
  │    ├─ pick angle bucket (weighted, history-aware)
  │    ├─ OpenAI Chat → hook + script + overlays + caption + hashtags + image_prompt
  │    ├─ OpenAI Images → image.jpg (1024x1536)
  │    ├─ OpenAI TTS → voiceover.mp3
  │    ├─ ffmpeg compose → video.mp4 (1080x1920, ~20-30s)
  │    └─ writes posts/<YYYY-MM-DD>/{image.jpg, voiceover.mp3, video.mp4, caption.txt, post.json}
  │
  ├─ git commit + push
  │
  └─ pipeline_publish.py  (skipped if no TIKTOK_ACCESS_TOKEN)
       └─ TikTok API: init upload → PUT video bytes → poll status → land in drafts
```

---

## Setup

### 1. OpenAI key

Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys), create a new secret key. Add credit at [platform.openai.com/account/billing](https://platform.openai.com/account/billing) — $5 lasts ~3 months.

### 2. TikTok Developer setup

a. Go to [developers.tiktok.com](https://developers.tiktok.com/) and log in with your TikTok account (same one you'll be posting from: `@thegadgetcity_01`).

b. Click **"Manage apps"** → **"Connect an app"** → name it `the-gadget-city`.

c. In the app dashboard, click **"Add products"** and add:
   - **Login Kit** — needed for OAuth.
   - **Content Posting API** — needed to upload videos.

d. Configure **Login Kit → Configuration**:
   - Redirect URI: `http://localhost:8765/cb`
   - Scopes (request): `user.info.basic`, `video.upload`, `video.publish`

e. Copy the **Client Key** and **Client Secret** from the app's "Basic Info" tab. You'll need them for step 3.

### 3. Get your TikTok access token

On your laptop, open Terminal and run:

```
cd ~/Documents/ig-auto-poster
pip install requests
TIKTOK_CLIENT_KEY=YOUR_CLIENT_KEY TIKTOK_CLIENT_SECRET=YOUR_CLIENT_SECRET python scripts/tiktok_oauth.py
```

A browser window opens → log into TikTok → approve the requested permissions → the script prints your `access_token` and `refresh_token`. **Save the refresh_token somewhere private** (you'll need it to refresh the access token; access tokens expire every 24 hours).

### 4. Set GitHub secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add two:

| Secret | Value |
|---|---|
| `OPENAI_API_KEY` | your OpenAI key from step 1 |
| `TIKTOK_ACCESS_TOKEN` | the access_token printed by the OAuth helper in step 3 |

### 5. First test run

Go to **Actions → Daily TikTok Post → "Run workflow"** button → check **dry_run** → green **Run workflow**.

The dry-run generates the video but does NOT upload. After ~2 minutes, look at `posts/<today's date>/` in your repo — you should see `image.jpg`, `voiceover.mp3`, `video.mp4`, `caption.txt`, `post.json`. Download `video.mp4` and watch it. If it looks good, run the workflow again with dry-run *unchecked*. The video will land in your TikTok Drafts inbox. Open the TikTok app → Profile → Drafts → tap the draft → review → Post.

### 6. Daily workflow takes over

The cron at 05:00 UTC runs every day. By 10am Pakistan / 1am ET, today's video is in your TikTok drafts. You spend 5 seconds tapping Post.

---

## Refreshing the TikTok token

Access tokens expire every ~24 hours. The cron will fail when that happens. Three options:

**A) Manual refresh, every day or two.** Run the helper:

```
TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=... python scripts/tiktok_oauth.py refresh <YOUR_REFRESH_TOKEN>
```

It prints a new access_token. Update the GitHub secret. (Annoying.)

**B) Auto-refresh in the workflow** *(recommended once you're up and running)*. We can add a step that, before publishing, exchanges the stored `TIKTOK_REFRESH_TOKEN` secret for a fresh access_token and uses it for that run only. The refresh token lasts a year. — Ask me to add this when you're ready.

**C) Apply for direct-publish + long-lived tokens via TikTok's app review.** Skip this until your account has 1,000+ followers; otherwise reviewers usually reject solo apps.

---

## Tuning content

`config/niches.yaml` controls the angle buckets and example angles. Higher `weight` = more frequently chosen. Adjust example angles to match your brand voice; the model uses them as style hints, not literal copies.

Default voiceover voice is `onyx` (warm, confident, male). To change: set `OPENAI_TTS_VOICE` in `.env` or as a workflow env var. Options: `alloy, echo, fable, onyx, nova, shimmer`.

---

## What this **does not** do (yet)

- Background music. (TikTok lets you add music in-app after posting.)
- Multiple voices / styles per video.
- Hashtag research from real-time TikTok trends.
- A/B testing of hooks.
- Reels/Instagram cross-posting (the same `video.mp4` works on IG Reels — drop it in the IG app manually).

These are all bolt-ons. Open an issue or just hack on it.

---

## Compliance notes

- Uses TikTok's **official Content Posting API** (Login Kit OAuth + `/v2/post/publish/...`). Allowed.
- Does **not** use any tool that logs into TikTok with your username + password. Those get accounts shadow-banned.
- AI-generated content: TikTok requires a "AI-generated" disclosure for synthetic content. Toggle it ON in your TikTok account settings (Settings → Privacy → AI-generated content) once, and TikTok will apply it to your uploads.
