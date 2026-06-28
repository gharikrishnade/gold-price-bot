"""
avatar_video.py — AI avatar video generation using HeyGen API
Generates a talking-head video of an avatar reading the gold price script.
"""

import requests
import os
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_BASE = "https://api.heygen.com"

# HeyGen avatar IDs — set these from your HeyGen dashboard
# You can use a single avatar for all languages, or different ones per language
DEFAULT_AVATAR = {
    "avatar_id": os.environ.get("HEYGEN_AVATAR_ID", "angela-inTalkshoq"),  # replace with yours
    "voice_id": None,  # Will be set per language
}

# HeyGen voice IDs per language
# Get these from HeyGen's voice list: https://docs.heygen.com/reference/list-voices
LANGUAGE_VOICES = {
    "tamil":     os.environ.get("HEYGEN_VOICE_TAMIL",     "ta-IN-PallaviNeural"),
    "telugu":    os.environ.get("HEYGEN_VOICE_TELUGU",    "te-IN-MohanNeural"),
    "kannada":   os.environ.get("HEYGEN_VOICE_KANNADA",   "kn-IN-SapnaNeural"),
    "malayalam": os.environ.get("HEYGEN_VOICE_MALAYALAM", "ml-IN-SobhanaNeural"),
    "hindi":     os.environ.get("HEYGEN_VOICE_HINDI",     "hi-IN-SwaraNeural"),
    "marathi":   os.environ.get("HEYGEN_VOICE_MARATHI",   "mr-IN-AarohiNeural"),
    "bengali":   os.environ.get("HEYGEN_VOICE_BENGALI",   "bn-IN-TanishaaNeural"),
}

# Per-language avatar overrides (optional — set to None to use default)
LANGUAGE_AVATARS = {
    "tamil":     os.environ.get("HEYGEN_AVATAR_TAMIL",     None),
    "telugu":    os.environ.get("HEYGEN_AVATAR_TELUGU",    None),
    "kannada":   os.environ.get("HEYGEN_AVATAR_KANNADA",   None),
    "malayalam": os.environ.get("HEYGEN_AVATAR_MALAYALAM", None),
    "hindi":     os.environ.get("HEYGEN_AVATAR_HINDI",     None),
    "marathi":   os.environ.get("HEYGEN_AVATAR_MARATHI",   None),
    "bengali":   os.environ.get("HEYGEN_AVATAR_BENGALI",   None),
}


def create_heygen_video(script: str, language: str, output_path: str) -> str:
    """
    Submit a video generation job to HeyGen, poll until done, download the video.
    Returns the local file path of the downloaded video.
    """
    avatar_id = LANGUAGE_AVATARS.get(language) or DEFAULT_AVATAR["avatar_id"]
    voice_id = LANGUAGE_VOICES.get(language)

    headers = {
        "X-Api-Key": HEYGEN_API_KEY,
        "Content-Type": "application/json",
    }

    # Step 1: Create video
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": voice_id,
                    "speed": 1.0,
                },
                "background": {
                    "type": "color",
                    "value": "#f5c518",  # Gold color background
                },
            }
        ],
        "dimension": {"width": 1920, "height": 1080},
        "aspect_ratio": "16:9",
        "caption": False,
    }

    logger.info(f"Submitting HeyGen job for language: {language}")
    resp = requests.post(
        f"{HEYGEN_BASE}/v2/video/generate",
        json=payload,
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"HeyGen API error: {data['error']}")

    video_id = data["data"]["video_id"]
    logger.info(f"HeyGen job submitted. video_id={video_id}")

    # Step 2: Poll for completion (typically 2-5 minutes)
    video_url = _poll_heygen_video(video_id, headers)

    # Step 3: Download video
    logger.info(f"Downloading video to {output_path}")
    _download_file(video_url, output_path)

    return output_path


def _poll_heygen_video(video_id: str, headers: dict, max_wait_secs: int = 600) -> str:
    """Poll HeyGen status endpoint until video is ready. Returns download URL."""
    poll_url = f"{HEYGEN_BASE}/v1/video_status.get?video_id={video_id}"
    waited = 0
    interval = 15  # seconds between polls

    while waited < max_wait_secs:
        time.sleep(interval)
        waited += interval

        resp = requests.get(poll_url, headers=headers, timeout=15)
        resp.raise_for_status()
        status_data = resp.json().get("data", {})
        status = status_data.get("status")

        logger.info(f"HeyGen status [{waited}s]: {status}")

        if status == "completed":
            return status_data["video_url"]
        elif status == "failed":
            raise RuntimeError(f"HeyGen video generation failed: {status_data.get('error')}")
        # else: processing/pending — keep polling

    raise TimeoutError(f"HeyGen video not ready after {max_wait_secs}s")


def _download_file(url: str, dest_path: str):
    """Download a file from URL to local path."""
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    logger.info(f"Downloaded {dest_path} ({Path(dest_path).stat().st_size // 1024} KB)")


def generate_all_videos(scripts: dict, output_dir: str = "output/videos") -> dict:
    """
    Generate videos for all language scripts.
    scripts: {state_key: {"language": ..., "script": ...}}
    Returns: {state_key: {"video_path": ..., ...}}
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = {}

    for state_key, data in scripts.items():
        if not data.get("script"):
            logger.warning(f"No script for {state_key}, skipping video")
            continue

        language = data["language"]
        date_str = data.get("date", "today").replace(" ", "_")
        output_path = f"{output_dir}/{state_key}_{date_str}.mp4"

        try:
            path = create_heygen_video(data["script"], language, output_path)
            results[state_key] = {**data, "video_path": path}
        except Exception as e:
            logger.error(f"Video generation failed for {state_key}: {e}")
            results[state_key] = {**data, "video_path": None, "error": str(e)}

    return results


def list_available_avatars() -> list:
    """Helper: list all available avatars in your HeyGen account."""
    headers = {"X-Api-Key": HEYGEN_API_KEY}
    resp = requests.get(f"{HEYGEN_BASE}/v2/avatars", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("avatars", [])


def list_available_voices(language_code: str = None) -> list:
    """Helper: list voices, optionally filtered by language code (e.g. 'ta', 'te')."""
    headers = {"X-Api-Key": HEYGEN_API_KEY}
    resp = requests.get(f"{HEYGEN_BASE}/v2/voices", headers=headers, timeout=15)
    resp.raise_for_status()
    voices = resp.json().get("data", {}).get("voices", [])
    if language_code:
        voices = [v for v in voices if v.get("language", "").startswith(language_code)]
    return voices


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # List available avatars
    print("Available avatars:")
    for av in list_available_avatars()[:5]:
        print(f"  {av.get('avatar_id')}: {av.get('avatar_name')}")
