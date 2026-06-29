"""
avatar_sadtalker.py — Local talking-head (lip-sync) generation via SadTalker.

Drives a single portrait image with our generated regional audio to produce a
lip-synced talking-head clip — fully local, no per-video cost. SadTalker is run as a
subprocess against its own checkout/venv so this repo doesn't take on its heavy deps.

Configuration (env):
  SADTALKER_DIR     path to the SadTalker repo (with inference.py + checkpoints).
  SADTALKER_PYTHON  python interpreter for SadTalker (default: "python").
  SADTALKER_ENHANCER optional face enhancer, e.g. "gfpgan" (slower, sharper).
  SADTALKER_EXTRA_ARGS  optional extra CLI args (space-separated).

If SADTALKER_DIR is unset or anything fails, render_talking_head() returns None so
the caller can fall back to the standard card/Ken-Burns video.

Tracker: AVATAR-001 (talking-avatar video for horoscope and other shows).
"""
from __future__ import annotations

import os
import shlex
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT_SECS = int(os.environ.get("SADTALKER_TIMEOUT", "1800"))


def is_configured() -> bool:
    d = os.environ.get("SADTALKER_DIR", "")
    return bool(d) and (Path(d) / "inference.py").exists()


def render_talking_head(image_path: str, audio_path: str, work_dir: str) -> str | None:
    """Run SadTalker(image + audio) → talking-head mp4. Returns path, or None on any issue."""
    if not is_configured():
        logger.info("SadTalker not configured (SADTALKER_DIR unset/invalid); skipping avatar render.")
        return None
    if not Path(image_path).exists():
        logger.warning(f"Avatar image not found: {image_path}; skipping avatar render.")
        return None
    if not Path(audio_path).exists():
        logger.warning(f"Avatar audio not found: {audio_path}; skipping avatar render.")
        return None

    sad_dir = Path(os.environ["SADTALKER_DIR"]).resolve()
    py = os.environ.get("SADTALKER_PYTHON", "python")
    result_dir = Path(work_dir).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        py, "inference.py",
        "--source_image", str(Path(image_path).resolve()),
        "--driven_audio", str(Path(audio_path).resolve()),
        "--result_dir", str(result_dir),
        "--preprocess", "full",   # keep the whole portrait, animate the face
        "--still",                # minimal head motion — steadier for a presenter
    ]
    enhancer = os.environ.get("SADTALKER_ENHANCER", "").strip()
    if enhancer:
        cmd += ["--enhancer", enhancer]
    extra = os.environ.get("SADTALKER_EXTRA_ARGS", "").strip()
    if extra:
        cmd += shlex.split(extra)

    logger.info(f"Running SadTalker: {' '.join(cmd)} (cwd={sad_dir})")
    try:
        proc = subprocess.run(
            cmd, cwd=str(sad_dir), timeout=_TIMEOUT_SECS,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"SadTalker timed out after {_TIMEOUT_SECS}s; falling back.")
        return None
    except Exception as e:
        logger.error(f"SadTalker failed to launch ({e}); falling back.")
        return None

    if proc.returncode != 0:
        logger.error(f"SadTalker exited {proc.returncode}; falling back.\nstderr tail:\n{proc.stderr[-800:]}")
        return None

    # SadTalker writes a timestamped mp4 under result_dir (sometimes in a subdir).
    mp4s = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        logger.error(f"SadTalker produced no mp4 in {result_dir}; falling back.")
        return None
    logger.info(f"SadTalker talking-head ready: {mp4s[0]}")
    return str(mp4s[0])
