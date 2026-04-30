"""One-time TikTok OAuth helper.

Run this on your laptop ONCE to get an access_token + refresh_token.
You then paste the access_token into your GitHub repo as the
TIKTOK_ACCESS_TOKEN secret. The token lasts ~24 hours; the refresh_token
lasts a year and is used to get fresh access tokens.

Prerequisites (do these on developers.tiktok.com first):
  1. Create a TikTok developer account.
  2. Create an app. Enable the "Login Kit" + "Content Posting API" products.
  3. In the app's settings, set "Redirect URI" to:  http://localhost:8765/cb
  4. Copy the Client Key and Client Secret.

Usage:
  $ pip install requests
  $ TIKTOK_CLIENT_KEY=awxxxxxx TIKTOK_CLIENT_SECRET=xxxx python scripts/tiktok_oauth.py
  -> Browser opens TikTok, you log in and approve.
  -> Script prints access_token and refresh_token. Paste access_token into
     your GitHub repo's Settings -> Secrets -> Actions as TIKTOK_ACCESS_TOKEN.

To refresh the token later:
  $ TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=... python scripts/tiktok_oauth.py refresh <refresh_token>
"""
from __future__ import annotations

import http.server
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import requests

CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8765/cb"
SCOPES = "user.info.basic,video.upload,video.publish"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


_received_code: dict[str, str] = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/cb":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        if "code" in qs:
            _received_code["code"] = qs["code"][0]
            _received_code["state"] = qs.get("state", [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Got it. You can close this tab.</h2>")
        else:
            err = qs.get("error_description", qs.get("error", ["unknown"]))[0]
            _received_code["error"] = err
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"<h2>Error: {err}</h2>".encode())


def _start_local_server() -> http.server.HTTPServer:
    server = http.server.HTTPServer(("localhost", 8765), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def authorize() -> dict:
    if not CLIENT_KEY or not CLIENT_SECRET:
        sys.exit("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET env vars.")

    state = secrets.token_urlsafe(16)
    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    server = _start_local_server()
    print("Opening browser for TikTok authorization...")
    print("If it doesn't open, paste this URL manually:")
    print(url)
    webbrowser.open(url)

    while not _received_code:
        pass

    if "error" in _received_code:
        sys.exit(f"Authorization failed: {_received_code['error']}")
    if _received_code.get("state") != state:
        sys.exit("State mismatch — possible CSRF, aborting.")

    code = _received_code["code"]
    print("Got authorization code, exchanging for tokens...")

    r = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    server.shutdown()
    return data


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
    print("\n=== SUCCESS ===")
    print(f"access_token  : {data.get('access_token')}")
    print(f"refresh_token : {data.get('refresh_token')}")
    print(f"expires_in    : {data.get('expires_in')} seconds")
    print(f"open_id       : {data.get('open_id')}")
    print()
    print("Next steps:")
    print(" 1. Copy the access_token above.")
    print(" 2. In your GitHub repo: Settings -> Secrets -> Actions ->")
    print("    New repository secret named TIKTOK_ACCESS_TOKEN, paste it.")
    print(" 3. SAVE the refresh_token somewhere private — you'll use it")
    print("    to refresh the access_token before it expires (every 24h).")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        token = sys.argv[2] if len(sys.argv) > 2 else input("refresh_token: ")
        _print_tokens(refresh(token))
    else:
        _print_tokens(authorize())
