"""
main.py — Daily Gold Price YouTube Bot Orchestrator

Run manually:   python main.py
Run with cron:  0 2 * * * /path/to/venv/bin/python /path/to/gold-price-bot/main.py
                (2:00 AM UTC = 7:30 AM IST)

Current pipeline (simple mode):
  1. Scrape gold prices per state
  2. Generate AI script in regional language (Claude)
  3. Generate thumbnail image (Pillow — 1280x720 JPEG)
  4. Generate voiceover audio (gTTS / Google Cloud TTS)
  5. Create video: thumbnail + Ken Burns effect + audio (MoviePy)
  6. Upload to YouTube channel (video + thumbnail)

AI avatar pipeline (HeyGen) is preserved in avatar_video.py.
To switch: replace steps 4-5 with create_heygen_video() from avatar_video.py.
"""

import os
import sys
import json
import logging
import argparse
from datetime import date
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Always load from the directory containing main.py (works regardless of cwd)
load_dotenv(Path(__file__).parent / ".env")

LOG_DIR = os.environ.get("LOG_DIR", "logs")
Path(LOG_DIR).mkdir(exist_ok=True)
today_str = date.today().isoformat()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/run_{today_str}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

from config import CHANNEL_CONFIG, DEFAULT_UPLOAD_PRIVACY
from scraper import get_state_prices
from script_generator import generate_script
from thumbnail_generator import generate_thumbnail
from tts_generator import generate_voiceover
from video_creator import create_video
from youtube_uploader import upload_video
from price_validator import validate_state_price_data
from price_history import build_history_context, store_price_data

RUN_OUTPUT_DIR = os.environ.get("RUN_OUTPUT_DIR", "output/runs")
UPLOAD_HISTORY_FILE = Path(LOG_DIR) / "upload_history.json"


def run_pipeline_for_state(
    state_key: str,
    config: dict,
    *,
    dry_run: bool = False,
    skip_upload: bool = False,
    privacy_status: str = DEFAULT_UPLOAD_PRIVACY,
    force_upload: bool = False,
) -> dict:
    """Run the full pipeline for one state/channel."""
    started_at = datetime.now().isoformat(timespec="seconds")
    result = {
        "run_date": today_str,
        "started_at": started_at,
        "state_key": state_key,
        "language": config["language"],
        "region_name": config.get("region_name"),
        "dry_run": dry_run,
        "privacy_status": privacy_status,
        "scrape_status": "pending",
        "price_validation_status": "pending",
        "script_generation_status": "pending",
        "thumbnail_status": "pending",
        "audio_status": "pending",
        "video_status": "pending",
        "history_storage_status": "pending",
        "upload_status": "pending",
    }
    language = config["language"]
    artifact_dir = _state_artifact_dir(state_key)
    result["artifact_dir"] = str(artifact_dir)

    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {state_key} ({language})")
    logger.info(f"{'='*60}")
    logger.info(f"Run options for {state_key}: dry_run={dry_run}, skip_upload={skip_upload}, privacy={privacy_status}")

    # ── Step 1: Scrape gold prices ────────────────────────────────────────────
    logger.info("[1/6] Scraping gold prices...")
    try:
        price_data = get_state_prices(state_key)
        result["price_data"] = price_data
        result["scrape_status"] = "success"

        validation = validate_state_price_data(price_data)
        result["price_validation"] = validation.to_dict()
        result["price_validation_status"] = "success" if validation.valid else "failed"
        if not validation.valid:
            for city_result in validation.city_results:
                if city_result.valid:
                    continue
                logger.error(
                    f"  Price validation failed for {state_key}/{city_result.city}: "
                    f"{'; '.join(city_result.errors)}"
                )
            result["error"] = "price_validation_failed"
            return result

        if price_data.get("cached"):
            logger.warning(
                f"  ⚠️  Market closed today — using last closing prices "
                f"from {price_data['cached_date']}"
            )
        logger.info(f"  ✅ Got prices for {len(price_data['cities'])} cities")
    except Exception as e:
        logger.exception(f"  ❌ Scraping failed for {state_key}: {e}")
        result["scrape_status"] = "failed"
        result["error"] = f"scraping: {e}"
        return result

    try:
        history_context = build_history_context(state_key, price_data, run_date=today_str)
        price_data["history_context"] = history_context
        result["history_context"] = history_context
        store_price_data(state_key, price_data, run_date=today_str)
        result["history_storage_status"] = "success"
    except Exception as e:
        logger.exception(f"  ❌ Historical price storage failed for {state_key}: {e}")
        result["history_storage_status"] = "failed"
        result["error"] = f"history_storage: {e}"
        return result

    # ── Step 2: Generate script ───────────────────────────────────────────────
    logger.info("[2/6] Generating AI script...")
    try:
        script = generate_script(language, state_key, price_data)
        result["script"] = script
        result["script_generation_status"] = "success"
        script_path = _write_script_artifact(artifact_dir, script)
        result["script_path"] = script_path
        logger.info(f"  ✅ Script generated ({len(script.split())} words)")
    except Exception as e:
        logger.exception(f"  ❌ Script generation failed for {state_key}: {e}")
        result["script_generation_status"] = "failed"
        result["error"] = f"script_gen: {e}"
        return result

    # ── Step 3: Generate thumbnail ────────────────────────────────────────────
    logger.info("[3/6] Generating thumbnail...")
    thumbnail_path = str(artifact_dir / "thumbnail.jpg")
    try:
        generate_thumbnail(language, state_key, price_data, thumbnail_path)
        result["thumbnail_path"] = thumbnail_path
        result["thumbnail_status"] = "success"
        logger.info(f"  ✅ Thumbnail: {thumbnail_path}")
    except Exception as e:
        logger.exception(f"  ⚠️  Thumbnail failed for {state_key} (non-fatal): {e}")
        result["thumbnail_status"] = "failed"
        result["thumbnail_error"] = str(e)
        thumbnail_path = None

    # ── Step 4: Generate voiceover ────────────────────────────────────────────
    logger.info("[4/6] Generating voiceover audio...")
    audio_path = str(artifact_dir / "voiceover.mp3")
    try:
        audio_path = _generate_voiceover_with_retries(script, language, audio_path, state_key)
        result["audio_path"] = audio_path
        result["audio_duration_seconds"] = _audio_duration_seconds(audio_path)
        result["audio_status"] = "success"
        logger.info(f"  ✅ Audio: {audio_path}")
    except Exception as e:
        logger.exception(f"  ❌ Voiceover failed for {state_key}: {e}")
        result["audio_status"] = "failed"
        result["error"] = f"tts: {e}"
        return result

    # ── Step 5: Create video ──────────────────────────────────────────────────
    logger.info("[5/6] Creating video (thumbnail + Ken Burns + audio)...")
    video_path = str(artifact_dir / "video.mp4")

    # If thumbnail failed, use a plain black frame fallback
    thumb_for_video = thumbnail_path if thumbnail_path else _make_fallback_thumbnail(
        language, price_data, str(artifact_dir / "thumbnail_fallback.jpg")
    )

    try:
        create_video(
            thumbnail_path=thumb_for_video,
            audio_path=audio_path,
            output_path=video_path,
            price_data=price_data,
            language=language,
        )
        result["video_path"] = video_path
        size_mb = Path(video_path).stat().st_size / (1024 * 1024)
        result["video_size_mb"] = round(size_mb, 2)
        result["video_status"] = "success"
        logger.info(f"  ✅ Video: {video_path} ({size_mb:.1f} MB)")
    except Exception as e:
        logger.exception(f"  ❌ Video creation failed for {state_key}: {e}")
        result["video_status"] = "failed"
        result["error"] = f"video: {e}"
        return result

    # ── Step 6: Upload to YouTube ─────────────────────────────────────────────
    if dry_run or skip_upload:
        reason = "dry_run" if dry_run else "skip_upload"
        result["upload_status"] = "skipped"
        result["upload_skip_reason"] = reason
        logger.info(f"[6/6] Upload skipped intentionally ({reason})")
        return result

    existing_upload = _find_existing_upload(state_key, today_str)
    if existing_upload and not force_upload:
        result["upload_status"] = "skipped"
        result["upload_skip_reason"] = "duplicate_upload_protection"
        result["youtube_video_id"] = existing_upload.get("video_id")
        result["youtube_url"] = existing_upload.get("url")
        logger.warning(
            f"[6/6] Upload skipped for {state_key}: already uploaded today. "
            f"Use --force-upload to override."
        )
        return result

    logger.info("[6/6] Uploading to YouTube...")
    token_file = config.get("youtube_token_file")
    try:
        video_id = upload_video(
            video_path=video_path,
            language=language,
            state_key=state_key,
            channel_token_file=token_file,
            thumbnail_path=thumbnail_path,
            privacy_status=privacy_status,
        )
        result["youtube_video_id"] = video_id
        result["youtube_url"] = f"https://youtu.be/{video_id}"
        result["upload_status"] = "success"
        _record_upload(state_key, today_str, video_id, result["youtube_url"], privacy_status)
        logger.info(f"  ✅ Live: https://youtu.be/{video_id}")
    except Exception as e:
        logger.exception(f"  ❌ Upload failed for {state_key}: {e}")
        result["upload_status"] = "failed"
        result["error"] = f"upload: {e}"

    return result


def _make_fallback_thumbnail(language: str, price_data: dict, path: str) -> str:
    """Black 1280x720 fallback thumbnail if generation failed."""
    try:
        from PIL import Image
        img = Image.new("RGB", (1280, 720), (20, 14, 2))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        img.save(path, "JPEG")
        return path
    except Exception:
        return None


def _run_artifact_dir() -> Path:
    path = Path(RUN_OUTPUT_DIR) / today_str
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_artifact_dir(state_key: str) -> Path:
    path = _run_artifact_dir() / state_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_script_artifact(artifact_dir: Path, script: str) -> str:
    script_path = artifact_dir / "script.txt"
    script_path.write_text(script, encoding="utf-8")
    return str(script_path)


def _audio_duration_seconds(audio_path: str) -> float | None:
    try:
        from moviepy import AudioFileClip
    except ImportError:
        try:
            from moviepy.editor import AudioFileClip
        except ImportError:
            return None

    audio = None
    try:
        audio = AudioFileClip(audio_path)
        return round(float(audio.duration), 2)
    except Exception as e:
        logger.warning(f"Could not determine audio duration for {audio_path}: {e}")
        return None
    finally:
        if audio:
            audio.close()


def _generate_voiceover_with_retries(script: str, language: str, audio_path: str, state_key: str) -> str:
    last_error = None
    for attempt in range(1, 4):
        try:
            return generate_voiceover(script, language, audio_path)
        except Exception as e:
            last_error = e
            if attempt == 3:
                break
            logger.warning(
                f"TTS failed for {state_key} on attempt {attempt}/3: {e}. Retrying..."
            )
    raise last_error


def _load_upload_history() -> dict:
    try:
        if UPLOAD_HISTORY_FILE.exists():
            return json.loads(UPLOAD_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not read upload history: {e}")
    return {}


def _find_existing_upload(state_key: str, run_date: str) -> dict | None:
    return _load_upload_history().get(run_date, {}).get(state_key)


def _record_upload(state_key: str, run_date: str, video_id: str, url: str, privacy_status: str) -> None:
    history = _load_upload_history()
    history.setdefault(run_date, {})[state_key] = {
        "video_id": video_id,
        "url": url,
        "privacy_status": privacy_status,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    UPLOAD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and optionally upload regional gold-price videos.")
    parser.add_argument("--dry-run", action="store_true", help="Generate local artifacts but skip YouTube upload.")
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload after local video generation.")
    parser.add_argument("--force-upload", action="store_true", help="Allow uploading even if this state/date was already uploaded.")
    parser.add_argument("--state", help="Process only one state key from CHANNEL_CONFIG.")
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default=DEFAULT_UPLOAD_PRIVACY,
        help=f"YouTube upload privacy. Default: {DEFAULT_UPLOAD_PRIVACY}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    args = _parse_args(argv)
    logger.info(f"🚀 Gold Price Bot starting — {today_str}")
    logger.info(
        f"Options: dry_run={args.dry_run}, skip_upload={args.skip_upload}, "
        f"state={args.state or 'enabled'}, privacy={args.privacy}, force_upload={args.force_upload}"
    )

    if args.state:
        if args.state not in CHANNEL_CONFIG:
            available = ", ".join(CHANNEL_CONFIG.keys())
            logger.error(f"Unknown state '{args.state}'. Available options: {available}")
            return 2
        enabled = {args.state: CHANNEL_CONFIG[args.state]}
    else:
        enabled = {k: v for k, v in CHANNEL_CONFIG.items() if v.get("enabled", True)}

    logger.info(f"Channels to process: {list(enabled.keys())}")

    all_results = {}
    for state_key, config in enabled.items():
        result = run_pipeline_for_state(
            state_key,
            config,
            dry_run=args.dry_run,
            skip_upload=args.skip_upload,
            privacy_status=args.privacy,
            force_upload=args.force_upload,
        )
        all_results[state_key] = result

    # Save summary
    summary_path = f"{LOG_DIR}/summary_{today_str}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    review_summary_path = _run_artifact_dir() / "summary.json"
    review_summary_path.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    success = [
        k for k, v in all_results.items()
        if v.get("upload_status") in {"success", "skipped"} and not v.get("error")
    ]
    failed  = [k for k, v in all_results.items() if v.get("error")]

    logger.info(f"\n{'='*60}")
    logger.info("DAILY RUN SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"✅ Completed ({len(success)}): {', '.join(success) or 'none'}")
    logger.info(f"❌ Failed  ({len(failed)}):  {', '.join(failed) or 'none'}")
    logger.info(f"Summary: {summary_path}")
    logger.info(f"Review summary: {review_summary_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
