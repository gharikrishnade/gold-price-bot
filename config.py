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

# ─── Channel Config (gold) ────────────────────────────────────────────────────
# The source of truth is jobs.yaml (see jobs_config.py). CHANNEL_CONFIG is derived
# from the gold jobs so existing gold importers keep working unchanged.
# Add or edit gold channels in jobs.yaml — no code change needed here.
from jobs_config import channel_config_for_module

CHANNEL_CONFIG = channel_config_for_module("gold")

# ─── Output directories ───────────────────────────────────────────────────────
VIDEO_OUTPUT_DIR = os.environ.get("VIDEO_OUTPUT_DIR", "output/videos")
LOG_DIR          = os.environ.get("LOG_DIR", "logs")

# ─── HeyGen Avatar ────────────────────────────────────────────────────────────
HEYGEN_DEFAULT_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID", "YOUR_AVATAR_ID_HERE")
