# iOS Shortcut — One-tap TikTok upload prep

This Shortcut turns your daily TikTok posting routine into ~10 seconds:
tap the Shortcut icon → today's video lands in Photos → caption copied to
clipboard → TikTok opens. Then: + → Upload → pick the latest video →
paste caption → Post.

## Setup (one-time, ~5 minutes)

### 1. Open the Shortcuts app on your iPhone

It's a built-in Apple app (the icon is two overlapping rectangles, blue/purple).
If you can't find it, search for "Shortcuts" in Spotlight. If it's been
deleted, reinstall it from the App Store (free).

### 2. Create a new Shortcut

1. Bottom of screen → tap **My Shortcuts** tab.
2. Top-right → tap the **+** button.
3. You're now in an empty Shortcut editor.
4. Top-center, tap "**New Shortcut**" → rename it to: `Daily Gadget Post`

### 3. Add these actions in this exact order

For each action, tap **Add Action** (or the search box at the bottom),
type the action name, tap to add it. Then configure as described.

**Action 1 — Get the date in YYYY-MM-DD format:**

- Search: **Current Date** → add it. (No config needed.)
- Search: **Format Date** → add it. Tap "Date" inside it → it should
  auto-fill to "Current Date". Change "Date Format" from "Short" to
  "Custom Format". In the Format String, type exactly: `yyyy-MM-dd`
- Search: **Set Variable** → add it. Set "Variable Name" to: `today`

**Action 2 — Download today's video to Photos:**

- Search: **Get Contents of URL** → add it. Tap the URL field. We need
  to build a URL with the date variable. Type:
  ```
  https://raw.githubusercontent.com/farhan0000/ig-auto-poster/main/posts/
  ```
  Then tap the variable picker (small icon to the right of the URL
  field) → pick **today**. Then continue typing:
  ```
  /video.mp4
  ```
  Final URL should look like:
  ```
  https://raw.githubusercontent.com/farhan0000/ig-auto-poster/main/posts/[today]/video.mp4
  ```
- Search: **Save to Photo Album** → add it. Default album "Recents" is fine.

**Action 3 — Download today's caption and copy to clipboard:**

- Search: **Get Contents of URL** → add it. Build this URL the same way:
  ```
  https://raw.githubusercontent.com/farhan0000/ig-auto-poster/main/posts/[today]/caption.txt
  ```
- Search: **Copy to Clipboard** → add it. (Default settings.)

**Action 4 — Open TikTok:**

- Search: **Open App** → add it. Tap "App" → search "TikTok" → select.

**Action 5 — Show a confirmation:**

- Search: **Show Notification** → add it. Title: `Daily post ready`.
  Body: `Video in Photos · Caption copied · Tap + Upload in TikTok`.

### 4. Save and add to home screen

1. Top-right → tap **Done** to save.
2. Long-press the Shortcut tile in My Shortcuts → tap **Share** →
   **Add to Home Screen**.
3. Pick an icon (you can use a saved image of the Gadget City logo) and
   a name. Tap **Add**.

You now have a Shortcut icon on your home screen.

## Daily routine

1. Tap the **Daily Gadget Post** icon on your home screen.
2. iOS shows a quick "Running shortcut..." indicator. ~3-5 seconds.
3. Notification: "Daily post ready · Video in Photos · Caption copied".
4. TikTok opens automatically.
5. Tap **+** at the bottom → **Upload** tab → pick the most recent video
   (it'll be at the top — that's what we just downloaded).
6. Tap **Next** → in the caption field, **tap and hold → Paste**.
7. Tap **Post**.

Total time: ~10 seconds.

## Troubleshooting

**"Couldn't get contents of URL"** — today's post hasn't been generated
yet. The cron runs at 05:00 UTC; if you're running this before that,
the video for today doesn't exist. Wait or use yesterday's date manually.

**"Save to Photo Album failed"** — first time only, iOS will ask for
permission to save photos. Allow it, then re-run.

**TikTok doesn't open** — first time only, iOS will ask permission for
the Shortcut to open apps. Allow.

**Wrong video appears in Photos** — sometimes iOS Photos sorts by date
taken, not date added. Sort by "Recently Added" or look at the top of
your camera roll.

## If the Shortcut breaks one day

The most likely cause: GitHub Actions failed to generate today's post.
Open the Actions tab on your repo and re-run the workflow manually. New
video lands in `posts/<date>/`, then re-run the Shortcut.
