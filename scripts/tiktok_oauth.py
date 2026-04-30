"""One-time TikTok OAuth helper (HTTPS-redirect / paste-code flow).

TikTok requires HTTPS redirect URIs, so we can't run a local callback
server. Instead, the redirect goes to a tiny page on your GitHub Pages
site (docs/oauth/index.html) which displays the OAuth `code` for you to
copy and paste back into this script.

Prereqs (one-time setup on developers.tiktok.com):
  1. Create app, add Login Kit + Content Posting API products.
  2. Set Login Kit Redirect URI to: https://YOUR_GH.github.io/ig-auto-poster/oauth/
  3. Add scopes: user.info.basic, video.upload, video.publish.
  4. Save.

Usage:
  $ pip install requests
  $ TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=... \
      python3 scripts/tiktok_oauth.py
  -> Browser opens TikTok auth.
  -> You log in, click Allow.
  -> Browser redirects to your GH Pages OAuth callback page; that page
     displays the `code` for you to copy.
  -> Paste the code back into the Terminal when prompted.
  -> Script exchanges it for access_token + refresh_token and prints them.

To refresh later:
  $ TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=... \
      python3 scripts/tiktok_oauth.py refresh <refresh_token>
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
import urllib.parse
import webbrowser

import requests

CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get(
    "TIKTOK_REDIRECT_URI",
    "https://farhan0000.github.io/ig-auto-poster/oauth/",
)
SCOPES = "user.info.basic,video.upload,video.publish"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def _pkce_pair() -> tuple[str, str]:
    """Generate a (code_verifier, code_challenge) pair for PKCE."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def authorize() -> dict:
    if not CLIENT_KEY or not CLIENT_SECRET:
        sys.exit("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET env vars.")

    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = _pkce_pair()
    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print()
    print("=" * 64)
    print("TikTok OAuth — Step 1: Authorize the app")
    print("=" * 64)
    print()
    print("Opening your browser to TikTok...")
    print("If it does not open, paste this URL into Chrome manually:")
    print()
    print(url)
    print()
    webbrowser.open(url)

    print("=" * 64)
    print("After you click Allow on TikTok, your browser will redirect to:")
    print(f"   {REDIRECT_URI}?code=XXXX&...")
    print()
    print("That page will display a `code` value with a 'Copy code' button.")
    print("Copy the code, then paste it below and press Enter.")
    print("=" * 64)
    print()

    code = input("Paste the code here: ").strip()
    if not code:
        sys.exit("No code entered, aborting.")

    print()
    print("Exchanging code for tokens...")
    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    if r.status_code >= 400:
        sys.exit(f"Token exchange failed [{r.status_code}]: {r.text}")
    return r.json()


def refresh(refresh_token: str) -> dict:
    if not CLIENT_KEY or not CLIENT_SECRET:
        sys.exit("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET env vars.")
    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _print_tokens(data: dict) -> None:
    print()
    print("=" * 64)
    print("SUCCESS")
    print("=" * 64)
    print(f"access_token  : {data.get('access_token')}")
    print(f"refresh_token : {data.get('refresh_token')}")
    print(f"expires_in    : {data.get('expires_in')} seconds")
    print(f"open_id       : {data.get('open_id')}")
    print(f"scope         : {data.get('scope')}")
    print()
    print("Next steps:")
    print(" 1. Copy the four secrets:")
    print("       TIKTOK_CLIENT_KEY      (the env var you set)")
    print("       TIKTOK_CLIENT_SECRET   (the env var you set)")
    print("       TIKTOK_ACCESS_TOKEN    (above)")
    print("       TIKTOK_REFRESH_TOKEN   (above)")
    print(" 2. In your GitHub repo: Settings → Secrets and variables → Actions")
    print("    → New repository secret. Paste each value into a separate secret.")
    print(" 3. Trigger the workflow manually to test.")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        token = sys.argv[2] if len(sys.argv) > 2 else input("refresh_token: ")
        _print_tokens(refresh(token))
    else:
        _print_tokens(authorize())
