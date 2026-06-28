"""
youtube_uploader.py — Upload gold price videos to YouTube channels
Uses YouTube Data API v3 with OAuth2 per channel.
"""

import os
import json
import logging
import time
from pathlib import Path
from datetime import date

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
UPLOAD_RETRIES = 3

# Credentials directory — one token file per channel
CREDS_DIR = Path(os.environ.get("YOUTUBE_CREDS_DIR", "credentials/youtube"))

# Video metadata templates per language
VIDEO_METADATA = {
    "tamil": {
        "title_template": "இன்றைய தங்கம் விலை {date} | Tamil Nadu Gold Rate Today | 22K & 24K",
        "description_template": (
            "இன்று {date} தமிழ்நாட்டில் தங்கம் விலை விவரங்கள்.\n\n"
            "📌 Chennai, Coimbatore, Madurai தங்கம் விலை\n"
            "📌 22 கேரட் மற்றும் 24 கேரட் தங்கம் விலை\n\n"
            "👍 Like செய்யுங்கள் | Subscribe செய்யுங்கள் | 🔔 Bell அடியுங்கள்\n\n"
            "#தங்கம்விலை #GoldRateToday #TamilNaduGoldRate #சென்னைதங்கம்"
        ),
        "tags": [
            "தங்கம் விலை", "gold rate today", "tamil gold rate",
            "chennai gold rate", "22k gold price", "24k gold price",
            "gold price tamil", "tamilnadu gold rate",
        ],
    },
    "telugu": {
        "title_template": "నేటి బంగారం ధర {date} | Telugu Gold Rate | 22K & 24K",
        "description_template": (
            "నేడు {date} బంగారం ధర వివరాలు.\n\n"
            "📌 తాజా నగరాల వారీ బంగారం ధర\n"
            "📌 22 కెరట్ మరియు 24 కెరట్ బంగారం ధర\n\n"
            "👍 Like | Subscribe | 🔔 Bell\n\n"
            "#బంగారంధర #GoldRateToday #TeluguGoldRate"
        ),
        "tags": [
            "బంగారం ధర", "gold rate today", "telugu gold rate",
            "22k gold price", "24k gold price",
        ],
    },
    "kannada": {
        "title_template": "ಇಂದಿನ ಚಿನ್ನದ ಬೆಲೆ {date} | Karnataka Gold Rate | 22K & 24K",
        "description_template": (
            "ಇಂದು {date} ಕರ್ನಾಟಕದಲ್ಲಿ ಚಿನ್ನದ ಬೆಲೆ ವಿವರಗಳು.\n\n"
            "📌 Bengaluru, Mysuru, Mangaluru ಚಿನ್ನದ ಬೆಲೆ\n"
            "👍 Like | Subscribe | 🔔 Bell\n\n"
            "#ಚಿನ್ನದಬೆಲೆ #KarnatakaGoldRate #BengaluruGoldRate"
        ),
        "tags": [
            "ಚಿನ್ನದ ಬೆಲೆ", "gold rate today", "karnataka gold rate",
            "bangalore gold rate", "22k gold price",
        ],
    },
    "malayalam": {
        "title_template": "ഇന്നത്തെ സ്വർണ്ണ വില {date} | Kerala Gold Rate | 22K & 24K",
        "description_template": (
            "ഇന്ന് {date} കേരളത്തിലെ സ്വർണ്ണ വില വിശദാംശങ്ങൾ.\n\n"
            "📌 Kochi, Thiruvananthapuram, Kozhikode സ്വർണ്ണ വില\n"
            "👍 Like | Subscribe | 🔔 Bell\n\n"
            "#സ്വർണ്ണവില #KeralaGoldRate #CochiGoldRate"
        ),
        "tags": [
            "സ്വർണ്ണ വില", "gold rate today", "kerala gold rate",
            "kochi gold rate", "22k gold price",
        ],
    },
    "hindi": {
        "title_template": "दिल्ली सोने का भाव {date} | Delhi Gold Rate Today | 22K & 24K",
        "description_template": (
            "आज {date} दिल्ली में सोने का भाव की पूरी जानकारी।\n\n"
            "📌 Delhi सोने का भाव\n"
            "📌 22 कैरेट और 24 कैरेट सोने की कीमत\n\n"
            "👍 Like करें | Subscribe करें | 🔔 Bell दबाएं\n\n"
            "#सोनेकाभाव #GoldRateToday #HindiGoldRate #DelhiGoldRate"
        ),
        "tags": [
            "सोने का भाव", "gold rate today", "hindi gold rate",
            "delhi gold rate", "22k gold price", "आज का सोना",
        ],
    },
    "marathi": {
        "title_template": "आजचा सोन्याचा भाव {date} | Maharashtra Gold Rate | 22K & 24K",
        "description_template": (
            "आज {date} महाराष्ट्रातील सोन्याचा भाव.\n\n"
            "📌 Mumbai, Pune, Nagpur सोन्याचा भाव\n"
            "👍 Like करा | Subscribe करा | 🔔 Bell दाबा\n\n"
            "#सोन्याचाभाव #MaharashtraGoldRate #MumbaiGoldRate"
        ),
        "tags": [
            "सोन्याचा भाव", "gold rate today", "maharashtra gold rate",
            "mumbai gold rate", "22k gold price",
        ],
    },
    "bengali": {
        "title_template": "আজকের সোনার দাম {date} | West Bengal Gold Rate | 22K & 24K",
        "description_template": (
            "আজ {date} পশ্চিমবঙ্গে সোনার দামের বিস্তারিত তথ্য।\n\n"
            "📌 Kolkata সোনার দাম\n"
            "👍 Like করুন | Subscribe করুন | 🔔 Bell চাপুন\n\n"
            "#সোনারদাম #WestBengalGoldRate #KolkataGoldRate"
        ),
        "tags": [
            "সোনার দাম", "gold rate today", "west bengal gold rate",
            "kolkata gold rate", "22k gold price",
        ],
    },
}

STATE_VIDEO_METADATA = {
    "andhra_pradesh": {
        "title_template": "ఆంధ్రప్రదేశ్ బంగారం ధర {date} | Andhra Pradesh Gold Rate Today | 22K & 24K",
        "description_template": (
            "నేడు {date} ఆంధ్రప్రదేశ్‌లో బంగారం ధర వివరాలు.\n\n"
            "📌 Vijayawada, Visakhapatnam, Guntur బంగారం ధర\n"
            "📌 22 కెరట్ మరియు 24 కెరట్ బంగారం ధర\n\n"
            "👍 Like | Subscribe | 🔔 Bell\n\n"
            "#బంగారంధర #GoldRateToday #AndhraPradeshGoldRate #VijayawadaGoldRate"
        ),
        "tags": [
            "బంగారం ధర", "gold rate today", "andhra pradesh gold rate",
            "vijayawada gold rate", "visakhapatnam gold rate", "guntur gold rate",
            "22k gold price", "24k gold price",
        ],
    },
    "telangana": {
        "title_template": "తెలంగాణ బంగారం ధర {date} | Telangana Gold Rate Today | 22K & 24K",
        "description_template": (
            "నేడు {date} తెలంగాణలో బంగారం ధర వివరాలు.\n\n"
            "📌 Hyderabad, Warangal బంగారం ధర\n"
            "📌 22 కెరట్ మరియు 24 కెరట్ బంగారం ధర\n\n"
            "👍 Like | Subscribe | 🔔 Bell\n\n"
            "#బంగారంధర #GoldRateToday #TelanganaGoldRate #HyderabadGoldRate"
        ),
        "tags": [
            "బంగారం ధర", "gold rate today", "telangana gold rate",
            "hyderabad gold rate", "warangal gold rate",
            "22k gold price", "24k gold price",
        ],
    },
}


def _get_youtube_service(channel_token_file: str):
    """Build authenticated YouTube service from stored OAuth token."""
    creds = None
    token_path = CREDS_DIR / channel_token_file

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                f"No valid credentials for {channel_token_file}. "
                f"Run: python setup_youtube_auth.py --channel {channel_token_file}"
            )
        # Save refreshed token
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def build_video_metadata(
    *,
    language: str,
    state_key: str,
    privacy_status: str = "private",
    upload_date: str = None,
) -> dict:
    """Build the exact YouTube metadata payload used for upload/review."""
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError(f"Invalid YouTube privacy status: {privacy_status}")

    date_label = upload_date or date.today().strftime("%d %B %Y")
    meta = STATE_VIDEO_METADATA.get(state_key, VIDEO_METADATA.get(language, {}))
    title = meta.get("title_template", "Gold Rate Today {date}").format(date=date_label)
    description = meta.get("description_template", "Gold rate update {date}").format(date=date_label)
    tags = meta.get("tags", ["gold rate", "gold price today"])

    return {
        "title": title[:100],
        "description": description[:5000],
        "tags": tags,
        "category_id": "25",
        "default_language": _yt_language_code(language),
        "privacy_status": privacy_status,
        "self_declared_made_for_kids": False,
    }


def upload_video(
    video_path: str,
    language: str,
    state_key: str,
    channel_token_file: str,
    thumbnail_path: str = None,
    privacy_status: str = "private",
) -> str:
    """
    Upload video to YouTube channel. Returns video ID.
    """
    metadata = build_video_metadata(
        language=language,
        state_key=state_key,
        privacy_status=privacy_status,
    )

    youtube = _get_youtube_service(channel_token_file)

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": metadata["category_id"],
            "defaultLanguage": metadata["default_language"],
        },
        "status": {
            "privacyStatus": metadata["privacy_status"],
            "selfDeclaredMadeForKids": metadata["self_declared_made_for_kids"],
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=4 * 1024 * 1024,  # 4MB chunks
    )

    logger.info(f"Uploading '{metadata['title']}' to YouTube with privacy={privacy_status}...")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = _next_chunk_with_retries(request)
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    logger.info(f"Upload complete! Video ID: {video_id}")

    # Set thumbnail if provided
    if thumbnail_path and Path(thumbnail_path).exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path),
        ).execute()
        logger.info("Thumbnail set.")

    return video_id


def _next_chunk_with_retries(request):
    last_error = None
    for attempt in range(1, UPLOAD_RETRIES + 1):
        try:
            return request.next_chunk()
        except Exception as e:
            last_error = e
            if attempt == UPLOAD_RETRIES:
                break
            wait_seconds = 5 * attempt
            logger.warning(
                f"YouTube upload chunk failed on attempt {attempt}/{UPLOAD_RETRIES}: {e}. "
                f"Retrying in {wait_seconds}s"
            )
            time.sleep(wait_seconds)
    raise last_error


def _yt_language_code(language: str) -> str:
    mapping = {
        "tamil": "ta",
        "telugu": "te",
        "kannada": "kn",
        "malayalam": "ml",
        "hindi": "hi",
        "marathi": "mr",
        "bengali": "bn",
    }
    return mapping.get(language, "en")


def upload_all_videos(video_data: dict) -> dict:
    """Upload all generated videos to their respective channels."""
    from config import CHANNEL_CONFIG, DEFAULT_UPLOAD_PRIVACY

    results = {}
    for state_key, data in video_data.items():
        if not data.get("video_path"):
            continue

        config = CHANNEL_CONFIG.get(state_key, {})
        token_file = config.get("youtube_token_file")
        if not token_file:
            logger.warning(f"No YouTube token configured for {state_key}")
            continue

        language = data["language"]
        try:
            video_id = upload_video(
                video_path=data["video_path"],
                language=language,
                state_key=state_key,
                channel_token_file=token_file,
                privacy_status=config.get("upload_privacy", DEFAULT_UPLOAD_PRIVACY),
            )
            results[state_key] = {**data, "youtube_video_id": video_id}
            logger.info(f"✅ {state_key}: https://youtu.be/{video_id}")
        except Exception as e:
            logger.error(f"Upload failed for {state_key}: {e}")
            results[state_key] = {**data, "youtube_video_id": None, "error": str(e)}

    return results
