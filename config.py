"""
config.py — Channel configuration
One entry per state/channel. Fill in your YouTube channel IDs and token file names.
"""

import os

# ─── API Keys (set in .env) ───────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HEYGEN_API_KEY    = os.environ.get("HEYGEN_API_KEY", "")

# Keep automated uploads private unless an operator explicitly changes it.
DEFAULT_UPLOAD_PRIVACY = os.environ.get("YOUTUBE_UPLOAD_PRIVACY", "private").lower()
if DEFAULT_UPLOAD_PRIVACY not in {"private", "unlisted", "public"}:
    DEFAULT_UPLOAD_PRIVACY = "private"

# ─── Channel Config ───────────────────────────────────────────────────────────
# language: which language to generate script + audio in
# region_name: human-readable region name used in prompts
# channel_id: your YouTube channel ID (UC...)
# youtube_token_file: filename inside credentials/youtube/ for this channel's OAuth token
# enabled: set to False to skip this channel

CHANNEL_CONFIG = {
    "tamil_nadu": {
        "language": "tamil",
        "region_name": "Tamil Nadu",
        "channel_id": os.environ.get("YT_CHANNEL_TAMIL", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "tamil_nadu.json",
        "enabled": False,
    },
    "andhra_pradesh": {
        "language": "telugu",
        "region_name": "Andhra Pradesh",
        "channel_id": os.environ.get("YT_CHANNEL_TELUGU_AP", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "andhra_pradesh.json",
        "enabled": True,
    },
    "telangana": {
        "language": "telugu",
        "region_name": "Telangana",
        "channel_id": os.environ.get("YT_CHANNEL_TELUGU_TS", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "telangana.json",
        "enabled": True,
    },
    "karnataka": {
        "language": "kannada",
        "region_name": "Karnataka",
        "channel_id": os.environ.get("YT_CHANNEL_KANNADA", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "karnataka.json",
        "enabled": False,
    },
    "kerala": {
        "language": "malayalam",
        "region_name": "Kerala",
        "channel_id": os.environ.get("YT_CHANNEL_MALAYALAM", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "kerala.json",
        "enabled": False,
    },
    "maharashtra": {
        "language": "marathi",
        "region_name": "Maharashtra",
        "channel_id": os.environ.get("YT_CHANNEL_MARATHI", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "maharashtra.json",
        "enabled": False,
    },
    "west_bengal": {
        "language": "bengali",
        "region_name": "West Bengal",
        "channel_id": os.environ.get("YT_CHANNEL_BENGALI", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "west_bengal.json",
        "enabled": False,
    },
    "delhi": {
        "language": "hindi",
        "region_name": "Delhi / North India",
        "channel_id": os.environ.get("YT_CHANNEL_HINDI", "UCxxxxxxxxxxxxxxxxx"),
        "youtube_token_file": "hindi_north.json",
        "enabled": False,
    },
    # Add more states below as needed
    # "gujarat": {
    #     "language": "gujarati",  # add gujarati to LANGUAGE_META if needed
    #     "region_name": "Gujarat",
    #     "channel_id": "UCxxxxxxxxxxxxxxxxx",
    #     "youtube_token_file": "gujarat.json",
    #     "enabled": False,
    # },
}

# ─── Output directories ───────────────────────────────────────────────────────
VIDEO_OUTPUT_DIR = os.environ.get("VIDEO_OUTPUT_DIR", "output/videos")
LOG_DIR          = os.environ.get("LOG_DIR", "logs")

# ─── HeyGen Avatar ────────────────────────────────────────────────────────────
HEYGEN_DEFAULT_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID", "YOUR_AVATAR_ID_HERE")
