"""
setup_youtube_auth.py — One-time OAuth setup per YouTube channel

Run this ONCE per channel on a machine with a browser:
  python setup_youtube_auth.py --channel tamil_nadu

It will open a browser, ask you to log into the YouTube channel's Google account,
and save the OAuth token to credentials/youtube/<channel>.json

After that, main.py will auto-refresh the token without browser interaction.
"""

import argparse
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from config import CHANNEL_CONFIG

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CREDS_DIR = Path("credentials/youtube")
CLIENT_SECRET_FILE = "credentials/google_client_secret.json"


def setup_auth(channel_key: str):
    config = CHANNEL_CONFIG.get(channel_key)
    if not config:
        print(f"❌ Unknown channel: {channel_key}")
        print(f"   Available: {list(CHANNEL_CONFIG.keys())}")
        return

    token_file = CREDS_DIR / config["youtube_token_file"]
    CREDS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n🔐 Setting up YouTube auth for: {channel_key}")
    print(f"   Language: {config['language']}")
    print(f"   Token will be saved to: {token_file}")
    print(f"\n   A browser will open. Log in to the CORRECT Google account")
    print(f"   (the one that owns the {config['language'].upper()} YouTube channel)\n")

    if not Path(CLIENT_SECRET_FILE).exists():
        print(f"❌ Missing: {CLIENT_SECRET_FILE}")
        print("   Download from Google Cloud Console → APIs & Services → Credentials")
        print("   Create OAuth 2.0 Client ID (Desktop app) → Download JSON")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_file, "w") as f:
        f.write(creds.to_json())

    print(f"\n✅ Token saved: {token_file}")
    print("   This channel is now authorized for automated uploads.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channel",
        required=True,
        help=f"Channel key from config.py. Options: {list(CHANNEL_CONFIG.keys())}",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Authorize all enabled channels one by one",
    )
    args = parser.parse_args()

    if args.all:
        for key, cfg in CHANNEL_CONFIG.items():
            if cfg.get("enabled"):
                setup_auth(key)
                input("\nPress Enter to continue to next channel...\n")
    else:
        setup_auth(args.channel)
