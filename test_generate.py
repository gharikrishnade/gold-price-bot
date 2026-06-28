"""
test_generate.py — Local test: thumbnail + audio + video
No external API keys needed.
TTS: edge-tts (free Microsoft Neural voice — requires internet)

Output: output/test_telugu_gold.mp4

Install deps first:
  pip install Pillow edge-tts moviepy imageio-ffmpeg numpy scipy
"""

import sys, os, logging
sys.path.insert(0, os.path.dirname(__file__))

# Load .env before importing any module that reads env vars
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test")

from pathlib import Path
from thumbnail_generator import generate_thumbnail

OUT_DIR = Path(__file__).parent / "output"
OUT_DIR.mkdir(exist_ok=True)

PRICE_DATA = {
    "date": "26 Jun 2026",
    "cities": {
        "Hyderabad":     {"22k_per_gram": 6750, "24k_per_gram": 7180, "22k_per_10g": 67500, "24k_per_10g": 71800},
        "Vijayawada":    {"22k_per_gram": 6745, "24k_per_gram": 7175, "22k_per_10g": 67450, "24k_per_10g": 71750},
        "Visakhapatnam": {"22k_per_gram": 6748, "24k_per_gram": 7178, "22k_per_10g": 67480, "24k_per_10g": 71780},
    },
}

SCRIPT = (
    "నమస్కారం! మీకు స్వాగతం. నేడు జూన్ 26, 2026. "
    "ఈరోజు ఆంధ్రప్రదేశ్ మరియు తెలంగాణలో బంగారం ధర వివరాలు. "
    "హైదరాబాద్‌లో 22 కెరట్ బంగారం ధర గ్రాముకు 6,750 రూపాయలు. "
    "24 కెరట్ బంగారం ధర గ్రాముకు 7,180 రూపాయలు. "
    "విజయవాడలో 22 కెరట్ 6,745 రూపాయలు, 24 కెరట్ 7,175 రూపాయలు. "
    "ప్రతిరోజూ బంగారం ధర అప్‌డేట్స్ కోసం మా చానెల్‌ను సబ్‌స్క్రైబ్ చేయండి. "
    "లైక్ చేయండి మరియు బెల్ నొక్కండి. ధన్యవాదాలు!"
)

THUMB_PATH = str(OUT_DIR / "test_thumbnail.jpg")
AUDIO_PATH = str(OUT_DIR / "test_audio.mp3")
VIDEO_PATH = str(OUT_DIR / "test_telugu_gold.mp4")

# ── Step 1: Thumbnail ─────────────────────────────────────────────────────────
logger.info("=" * 55)
logger.info("Step 1/3 — Generating thumbnail (Sample B)...")
logger.info("=" * 55)
generate_thumbnail("telugu", "andhra_pradesh", PRICE_DATA, THUMB_PATH)
logger.info(f"✅ Thumbnail: {THUMB_PATH}\n")

# ── Step 2: Audio — edge-tts (free Microsoft Neural voice) ───────────────────
logger.info("=" * 55)
logger.info("Step 2/3 — Generating Telugu voiceover (edge-tts)...")
logger.info("=" * 55)

from tts_generator import generate_voiceover
actual_audio_path = generate_voiceover(SCRIPT, "telugu", AUDIO_PATH)
logger.info(f"✅ Audio: {actual_audio_path}")

logger.info("")

# ── Step 3: Video ─────────────────────────────────────────────────────────────
logger.info("=" * 55)
logger.info("Step 3/3 — Creating video (static + fade)...")
logger.info("=" * 55)
from video_creator import create_video
# Use actual_audio_path (may be .wav if conversion failed — moviepy handles both)
# Pass state_key so video_creator renders the frame natively at 1920×1080
create_video(THUMB_PATH, actual_audio_path, VIDEO_PATH, PRICE_DATA, "telugu", state_key="andhra_pradesh")

size_mb = Path(VIDEO_PATH).stat().st_size / 1024 / 1024
logger.info(f"\n✅ Done! Video: {VIDEO_PATH}  ({size_mb:.1f} MB)")
