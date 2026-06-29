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

from config import DEFAULT_UPLOAD_PRIVACY
from modules import get_module
from jobs_config import load_jobs, get_job
from tts_generator import generate_voiceover
from video_creator import create_vertical_video, create_video, save_trend_preview
from youtube_uploader import upload_video
from notifier import notifications_enabled, send_run_notification
from review_page import write_review_page

RUN_OUTPUT_DIR = os.environ.get("RUN_OUTPUT_DIR", "output/runs")
UPLOAD_HISTORY_FILE = Path(LOG_DIR) / "upload_history.json"
APPROVAL_MARKER_FILE = os.environ.get("UPLOAD_APPROVAL_MARKER", "APPROVED_FOR_UPLOAD")
APPROVAL_INSTRUCTIONS_FILE = "UPLOAD_APPROVAL_REQUIRED.txt"
DEFAULT_REQUIRE_UPLOAD_APPROVAL = os.environ.get("REQUIRE_UPLOAD_APPROVAL", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def run_pipeline_for_channel(
    module,
    state_key: str,
    *,
    dry_run: bool = False,
    skip_upload: bool = False,
    privacy_status: str = DEFAULT_UPLOAD_PRIVACY,
    force_upload: bool = False,
    create_shorts: bool = False,
    shorts_only: bool = False,
    trend_cards: bool = False,
    require_approval: bool = DEFAULT_REQUIRE_UPLOAD_APPROVAL,
) -> dict:
    """Run the full pipeline for one channel of the given content module."""
    if shorts_only:
        create_shorts = True
    config = module.channel_meta(state_key)
    language = module.language_for(state_key)
    started_at = datetime.now().isoformat(timespec="seconds")
    result = {
        "run_date": today_str,
        "started_at": started_at,
        "module": module.key,
        "state_key": state_key,
        "language": language,
        "region_name": config.get("region_name"),
        "dry_run": dry_run,
        "privacy_status": privacy_status,
        "create_shorts": create_shorts,
        "shorts_only": shorts_only,
        "trend_cards": trend_cards,
        "require_upload_approval": require_approval,
        "scrape_status": "pending",
        "price_validation_status": "pending",
        "script_generation_status": "pending",
        "thumbnail_status": "pending",
        "audio_status": "pending",
        "video_status": "pending",
        "trend_cards_status": "not_requested",
        "shorts_status": "not_requested",
        "history_storage_status": "pending",
        "upload_status": "pending",
    }
    artifact_dir = _state_artifact_dir(state_key)
    result["artifact_dir"] = str(artifact_dir)
    result["approval_marker_path"] = str(_approval_marker_path(artifact_dir))

    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {module.key}/{state_key} ({language})")
    logger.info(f"{'='*60}")
    logger.info(
        f"Run options for {state_key}: dry_run={dry_run}, skip_upload={skip_upload}, "
        f"privacy={privacy_status}, shorts={create_shorts}, shorts_only={shorts_only}, "
        f"trend_cards={trend_cards}, require_approval={require_approval}"
    )

    # ── Step 1: Fetch + validate data ─────────────────────────────────────────
    logger.info(f"[1/6] Fetching data ({module.key})...")
    try:
        price_data = module.fetch(state_key)
        result["price_data"] = price_data
        result["scrape_status"] = "success"

        validation = module.validate(price_data)
        result["price_validation"] = validation.details
        result["price_validation_status"] = "success" if validation.valid else "failed"
        if not validation.valid:
            for err in validation.errors:
                logger.error(f"  Data validation failed for {state_key}: {err}")
            result["error"] = "price_validation_failed"
            return result

        if price_data.get("cached"):
            logger.warning(
                f"  ⚠️  Market closed today — using last closing prices "
                f"from {price_data['cached_date']}"
            )
        logger.info(f"  ✅ Got data for {len(price_data.get('cities', {}))} cities")
    except Exception as e:
        logger.exception(f"  ❌ Fetch failed for {state_key}: {e}")
        result["scrape_status"] = "failed"
        result["error"] = f"fetch: {e}"
        return result

    if module.needs_history:
        try:
            history_context = module.build_history(state_key, price_data, run_date=today_str)
            result["history_context"] = history_context
            result["history_storage_status"] = "success"
        except Exception as e:
            logger.exception(f"  ❌ History storage failed for {state_key}: {e}")
            result["history_storage_status"] = "failed"
            result["error"] = f"history_storage: {e}"
            return result
    else:
        result["history_storage_status"] = "not_applicable"

    # ── Shorts-only mode: skip the long landscape video pipeline entirely ──────
    if shorts_only:
        logger.info("Shorts-only mode: skipping long landscape script/thumbnail/voiceover/video.")
        for skipped in ("script_generation_status", "thumbnail_status", "audio_status", "video_status"):
            result[skipped] = "skipped_shorts_only"
        _create_shorts_video(result, artifact_dir, module, state_key, price_data)

        # ── Step 6: Upload the Short ───────────────────────────────────────────
        if dry_run or skip_upload:
            reason = "dry_run" if dry_run else "skip_upload"
            result["upload_status"] = "skipped"
            result["upload_skip_reason"] = reason
            logger.info(f"[6/6] Upload skipped intentionally ({reason})")
        elif result.get("shorts_status") != "success":
            result["upload_status"] = "skipped"
            result["upload_skip_reason"] = "shorts_not_created"
            logger.warning("[6/6] Upload skipped: Short was not created successfully.")
        else:
            _upload_short_video(
                result, artifact_dir, module, state_key, language, privacy_status,
                require_approval=require_approval, force_upload=force_upload,
            )
        return result

    # ── Step 2: Generate script ───────────────────────────────────────────────
    logger.info("[2/6] Generating AI script...")
    try:
        script = module.generate_script(state_key, price_data)
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
        module.render_thumbnail(state_key, price_data, thumbnail_path)
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
        if trend_cards:
            trend_preview_path = str(artifact_dir / "trend_preview.jpg")
            preview_path = save_trend_preview(
                thumbnail_path=thumb_for_video,
                output_path=trend_preview_path,
                price_data=price_data,
                language=language,
                state_key=state_key,
            )
            if preview_path:
                result["trend_preview_path"] = preview_path
                result["trend_cards_status"] = "success"
            else:
                result["trend_cards_status"] = "skipped_no_history"

        create_video(
            thumbnail_path=thumb_for_video,
            audio_path=audio_path,
            output_path=video_path,
            price_data=price_data,
            language=language,
            state_key=state_key,
            enable_trend_cards=trend_cards,
        )
        result["video_path"] = video_path
        size_mb = Path(video_path).stat().st_size / (1024 * 1024)
        result["video_size_mb"] = round(size_mb, 2)
        result["video_status"] = "success"
        result["youtube_metadata"] = module.youtube_metadata(state_key, privacy_status)
        logger.info(f"  ✅ Video: {video_path} ({size_mb:.1f} MB)")
    except Exception as e:
        logger.exception(f"  ❌ Video creation failed for {state_key}: {e}")
        result["video_status"] = "failed"
        result["error"] = f"video: {e}"
        return result

    if create_shorts:
        logger.info("[5b/6] Creating vertical Shorts/Reels video...")
        _create_shorts_video(result, artifact_dir, module, state_key, price_data)

    # ── Step 6: Upload to YouTube ─────────────────────────────────────────────
    if dry_run or skip_upload:
        reason = "dry_run" if dry_run else "skip_upload"
        result["upload_status"] = "skipped"
        result["upload_skip_reason"] = reason
        logger.info(f"[6/6] Upload skipped intentionally ({reason})")
        return result

    if require_approval and not _upload_approved(artifact_dir):
        marker_path = _approval_marker_path(artifact_dir)
        instructions_path = _write_approval_instructions(artifact_dir, marker_path, state_key)
        result["upload_status"] = "skipped"
        result["upload_skip_reason"] = "manual_approval_required"
        result["approval_instructions_path"] = str(instructions_path)
        logger.warning(
            f"[6/6] Upload skipped for {state_key}: manual approval required. "
            f"Review artifacts and create {marker_path} to approve upload."
        )
        return result

    run_key = _run_key(module.key, state_key)
    existing_upload = _find_existing_upload(run_key, today_str)
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
        _record_upload(run_key, today_str, video_id, result["youtube_url"], privacy_status)
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


def _create_shorts_video(result, artifact_dir, module, state_key, price_data):
    """Build the vertical Shorts/Reels video: short script + own voiceover + portrait template.

    Self-contained — does not depend on the long landscape video's artifacts, so it also
    works in shorts-only mode. Mutates ``result`` with status/paths.
    """
    language = module.language_for(state_key)
    shorts_path = str(artifact_dir / "shorts.mp4")
    try:
        # Short, punchy ~30s script + its own voiceover so the Short stays under a minute.
        short_script = module.generate_short_script(state_key, price_data)
        short_script_path = artifact_dir / "shorts_script.txt"
        short_script_path.write_text(short_script, encoding="utf-8")
        result["shorts_script_path"] = str(short_script_path)

        shorts_audio_path = _generate_voiceover_with_retries(
            short_script, language, str(artifact_dir / "shorts_voiceover.mp3"), state_key
        )
        result["shorts_audio_path"] = shorts_audio_path

        # Purpose-built portrait 9:16 template that fills the screen.
        shorts_thumb_path = str(artifact_dir / "shorts_thumbnail.jpg")
        module.render_vertical_thumbnail(state_key, price_data, shorts_thumb_path)
        result["shorts_thumbnail_path"] = shorts_thumb_path

        create_vertical_video(
            thumbnail_path=shorts_thumb_path,
            audio_path=shorts_audio_path,
            output_path=shorts_path,
            vertical_frame_path=shorts_thumb_path,
        )
        result["shorts_video_path"] = shorts_path
        shorts_size_mb = Path(shorts_path).stat().st_size / (1024 * 1024)
        result["shorts_video_size_mb"] = round(shorts_size_mb, 2)
        result["shorts_duration_seconds"] = _audio_duration_seconds(shorts_audio_path)
        result["shorts_status"] = "success"
        logger.info(
            f"  ✅ Shorts/Reels video: {shorts_path} ({shorts_size_mb:.1f} MB, "
            f"{result['shorts_duration_seconds'] or 0:.0f}s)"
        )
    except Exception as e:
        logger.exception(f"  ❌ Shorts/Reels video creation failed for {state_key}: {e}")
        result["shorts_status"] = "failed"
        result["shorts_error"] = str(e)


def _upload_short_video(
    result, artifact_dir, module, state_key, language, privacy_status,
    *, require_approval, force_upload,
):
    """Upload the vertical Short to YouTube. Mirrors Step 6 but targets the shorts file.

    Assumes dry_run / skip_upload are already handled by the caller. Short uploads are
    tracked under a ``<module>:<channel>__shorts`` history key so they don't clash with the long video.
    """
    if require_approval and not _upload_approved(artifact_dir):
        marker_path = _approval_marker_path(artifact_dir)
        instructions_path = _write_approval_instructions(artifact_dir, marker_path, state_key)
        result["upload_status"] = "skipped"
        result["upload_skip_reason"] = "manual_approval_required"
        result["approval_instructions_path"] = str(instructions_path)
        logger.warning(
            f"[6/6] Short upload skipped for {state_key}: manual approval required. "
            f"Review artifacts and create {marker_path} to approve upload."
        )
        return

    short_key = f"{_run_key(module.key, state_key)}__shorts"
    existing_upload = _find_existing_upload(short_key, today_str)
    if existing_upload and not force_upload:
        result["upload_status"] = "skipped"
        result["upload_skip_reason"] = "duplicate_upload_protection"
        result["youtube_video_id"] = existing_upload.get("video_id")
        result["youtube_url"] = existing_upload.get("url")
        logger.warning(
            f"[6/6] Short upload skipped for {state_key}: already uploaded today. "
            f"Use --force-upload to override."
        )
        return

    logger.info("[6/6] Uploading Short to YouTube...")
    token_file = module.channel_meta(state_key).get("youtube_token_file")
    try:
        video_id = upload_video(
            video_path=result["shorts_video_path"],
            language=language,
            state_key=state_key,
            channel_token_file=token_file,
            thumbnail_path=result.get("shorts_thumbnail_path"),
            privacy_status=privacy_status,
            shorts=True,
        )
        result["youtube_video_id"] = video_id
        result["youtube_url"] = f"https://youtu.be/{video_id}"
        result["upload_status"] = "success"
        _record_upload(short_key, today_str, video_id, result["youtube_url"], privacy_status)
        logger.info(f"  ✅ Live (Short): https://youtu.be/{video_id}")
    except Exception as e:
        logger.exception(f"  ❌ Short upload failed for {state_key}: {e}")
        result["upload_status"] = "failed"
        result["error"] = f"upload: {e}"


def _approval_marker_path(artifact_dir: Path) -> Path:
    return artifact_dir / APPROVAL_MARKER_FILE


def _upload_approved(artifact_dir: Path) -> bool:
    return _approval_marker_path(artifact_dir).exists()


def _write_approval_instructions(artifact_dir: Path, marker_path: Path, state_key: str) -> Path:
    instructions_path = artifact_dir / APPROVAL_INSTRUCTIONS_FILE
    instructions_path.write_text(
        "\n".join(
            [
                f"Manual upload approval is required for {state_key} on {today_str}.",
                f"Review the artifacts in this folder, then create {marker_path.name} in this folder to approve upload.",
                "The bot checks for the marker file path, not the marker file's contents.",
                "Delete the marker file to require approval again on a rerun.",
            ]
        ),
        encoding="utf-8",
    )
    return instructions_path


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


def _run_key(module_key: str, channel: str) -> str:
    """Dedupe/history key that is unique across modules (PLAT-008)."""
    return f"{module_key}:{channel}"


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
    parser = argparse.ArgumentParser(description="Generate and optionally upload regional content videos.")
    parser.add_argument("--job", help="Run a single job by id from jobs.yaml (overrides --module/--state).")
    parser.add_argument("--module", help="Run only jobs for this content module / show (default: all modules).")
    parser.add_argument("--dry-run", action="store_true", help="Generate local artifacts but skip YouTube upload.")
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload after local video generation.")
    parser.add_argument("--force-upload", action="store_true", help="Allow uploading even if this state/date was already uploaded.")
    parser.add_argument("--shorts", action="store_true", help="Also create a vertical 9:16 Shorts/Reels MP4.")
    parser.add_argument("--shorts-only", action="store_true", help="Create ONLY the vertical Shorts/Reels MP4 — skip the long landscape video.")
    parser.add_argument("--trend-cards", action="store_true", help="Add an animated regional trend-card segment when price history exists.")
    parser.add_argument(
        "--require-approval",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_REQUIRE_UPLOAD_APPROVAL,
        help="Skip upload unless the state artifact folder contains the upload approval marker.",
    )
    parser.add_argument("--no-notify", action="store_true", help="Do not send configured run notifications.")
    parser.add_argument("--state", help="Process only one channel key for the selected module.")
    parser.add_argument(
        "--privacy",
        choices=("private", "unlisted", "public"),
        default=DEFAULT_UPLOAD_PRIVACY,
        help=f"YouTube upload privacy. Default: {DEFAULT_UPLOAD_PRIVACY}",
    )
    return parser.parse_args(argv)


def _select_jobs(args) -> list:
    """Pick which jobs to run from jobs.yaml based on CLI filters.

    --job selects one job explicitly (even if disabled). Otherwise start from all
    jobs, narrow by --module and/or --state (channel); --state is treated as an
    explicit selection so a disabled channel can still be run on demand. With no
    filters, run every enabled job.
    """
    jobs = load_jobs()
    if args.job:
        return [get_job(args.job)]
    if args.module:
        jobs = [j for j in jobs if j.module == args.module]
    if args.state:
        selected = [j for j in jobs if j.channel == args.state]
        if not selected:
            scope = f" for module '{args.module}'" if args.module else ""
            channels = ", ".join(sorted({j.channel for j in jobs})) or "none"
            raise KeyError(f"No job with channel '{args.state}'{scope}. Channels: {channels}")
        return selected
    return [j for j in jobs if j.enabled]


def _resolve_formats(args, job) -> tuple[bool, bool]:
    """Decide (create_shorts, shorts_only). CLI flags win; else use the job's formats."""
    if args.shorts_only:
        return True, True
    if args.shorts:
        return True, False
    formats = job.formats or ["long"]
    if formats == ["short"]:
        return True, True          # short-only job
    if "short" in formats:
        return True, False         # long + short
    return False, False            # long only


def main(argv: list[str] | None = None):
    args = _parse_args(argv)
    try:
        jobs = _select_jobs(args)
    except (KeyError, FileNotFoundError, ValueError) as e:
        logger.error(str(e).strip('"'))
        return 2
    if not jobs:
        logger.error("No matching jobs to run (check jobs.yaml and your filters).")
        return 2

    logger.info(f"🚀 Content bot starting — {today_str}")
    logger.info(
        f"Options: job={args.job or '-'}, module={args.module or 'all'}, "
        f"channel={args.state or '-'}, dry_run={args.dry_run}, skip_upload={args.skip_upload}, "
        f"privacy={args.privacy}, force_upload={args.force_upload}, "
        f"require_approval={args.require_approval}, shorts={args.shorts}, "
        f"shorts_only={args.shorts_only}, trend_cards={args.trend_cards}, notify={not args.no_notify}"
    )
    logger.info("Jobs to process: " + ", ".join(j.id for j in jobs))

    # Resolve modules and run preflight per module on its selected channels.
    from collections import defaultdict
    channels_by_module: dict[str, list[str]] = defaultdict(list)
    for j in jobs:
        channels_by_module[j.module].append(j.channel)
    modules_by_key = {}
    for mkey, chans in channels_by_module.items():
        try:
            modules_by_key[mkey] = get_module(mkey)
        except KeyError as e:
            logger.error(str(e).strip('"'))
            return 2
        if not modules_by_key[mkey].preflight(chans):
            return 1

    all_results = {}
    for j in jobs:
        module = modules_by_key[j.module]
        create_shorts, shorts_only = _resolve_formats(args, j)
        result = run_pipeline_for_channel(
            module,
            j.channel,
            dry_run=args.dry_run,
            skip_upload=args.skip_upload,
            privacy_status=args.privacy,
            force_upload=args.force_upload,
            create_shorts=create_shorts,
            shorts_only=shorts_only,
            trend_cards=args.trend_cards,
            require_approval=args.require_approval,
        )
        result["job_id"] = j.id
        all_results[j.id] = result

    # Save summary
    summary_path = f"{LOG_DIR}/summary_{today_str}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    review_summary_path = _run_artifact_dir() / "summary.json"
    review_summary_path.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    review_page_path = _run_artifact_dir() / "review.html"
    try:
        write_review_page(
            all_results,
            output_path=review_page_path,
            summary_path=summary_path,
            review_summary_path=str(review_summary_path),
        )
    except Exception as e:
        logger.warning(f"Could not write review page: {e}")
        review_page_path = None

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
    if review_page_path:
        logger.info(f"Review page: {review_page_path}")

    if args.no_notify:
        logger.info("Notifications skipped by --no-notify")
    elif notifications_enabled():
        notification_status = send_run_notification(
            all_results,
            summary_path=summary_path,
            review_summary_path=str(review_summary_path),
            review_page_path=str(review_page_path) if review_page_path else None,
        )
        logger.info(f"Notification status: {notification_status}")
    else:
        logger.info("Notifications not configured; skipping")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
