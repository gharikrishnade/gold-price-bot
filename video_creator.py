"""
video_creator.py — Create YouTube video from thumbnail image + TTS audio

Compatible with moviepy 1.x AND 2.x.

Video structure (matches audio duration):
  0.0s  → 1.2s  : Fade in
  1.2s  → end   : Ken Burns slow zoom (1.0x → 1.03x)  [very subtle]
  end-1.5s → end: Fade out

Output: 1920x1080, H.264
"""

import os
import sys
import tempfile
import logging
import numpy as np
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

OUT_W, OUT_H = 1920, 1080
FPS = 24
FADE_IN  = 1.2
FADE_OUT = 1.5
ZOOM_START = 1.0
ZOOM_END   = 1.0    # no zoom — static image with fade in/out only


def _import_moviepy():
    """Import moviepy, handling both v1.x and v2.x API differences."""
    try:
        # moviepy 2.x
        from moviepy import VideoClip, AudioFileClip, CompositeVideoClip
        import moviepy.video.fx as vfx

        def apply_fades(clip):
            return clip.with_effects([vfx.FadeIn(FADE_IN), vfx.FadeOut(FADE_OUT)])

        def set_audio(clip, audio):
            return clip.with_audio(audio)

        def set_fps(clip, fps):
            return clip.with_fps(fps)

        logger.info("Using moviepy 2.x")
        return VideoClip, AudioFileClip, CompositeVideoClip, apply_fades, set_audio, set_fps, "v2"

    except ImportError:
        # moviepy 1.x
        from moviepy.editor import VideoClip, AudioFileClip, CompositeVideoClip
        from moviepy.video.fx.fadein import fadein
        from moviepy.video.fx.fadeout import fadeout

        def apply_fades(clip):
            return fadeout(fadein(clip, FADE_IN), FADE_OUT)

        def set_audio(clip, audio):
            return clip.set_audio(audio)

        def set_fps(clip, fps):
            return clip.set_fps(fps)

        logger.info("Using moviepy 1.x")
        return VideoClip, AudioFileClip, CompositeVideoClip, apply_fades, set_audio, set_fps, "v1"


def create_video(
    thumbnail_path: str,
    audio_path: str,
    output_path: str,
    price_data: dict = None,
    language: str = "hindi",
    state_key: str = None,
) -> str:
    """
    Combine thumbnail + audio into a video with Ken Burns zoom + fade transitions.

    If price_data + state_key + language are supplied, re-renders the thumbnail
    natively at 1920×1080 so fonts are crisp (no JPEG upscale blur).
    Falls back to LANCZOS-upscaling the JPEG if those aren't available.

    Returns output_path.
    """
    VideoClip, AudioFileClip, CompositeVideoClip, apply_fades, set_audio, set_fps, ver = _import_moviepy()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Audio ─────────────────────────────────────────────────────────────────
    logger.info(f"Loading audio: {audio_path}")
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    logger.info(f"  Duration: {duration:.1f}s")

    # ── Build HD frame ────────────────────────────────────────────────────────
    # Prefer native 1920×1080 render (crisp fonts) over upscaling the JPEG.
    if price_data and state_key and language:
        try:
            bot_dir = str(Path(__file__).parent)
            if bot_dir not in sys.path:
                sys.path.insert(0, bot_dir)
            from thumbnail_generator import generate_thumbnail
            import tempfile as _tf
            hd_tmp = _tf.mktemp(suffix="_hd.jpg")
            logger.info("Rendering HD thumbnail natively at 1920×1080…")
            generate_thumbnail(language, state_key, price_data, hd_tmp, width=OUT_W, height=OUT_H)
            img_array = np.array(Image.open(hd_tmp).convert("RGB"))
            logger.info("  ✅ Native HD frame ready")
        except Exception as e:
            logger.warning(f"Native HD render failed ({e}), falling back to JPEG upscale")
            img_array = np.array(
                Image.open(thumbnail_path).convert("RGB").resize((OUT_W, OUT_H), Image.LANCZOS)
            )
    else:
        logger.info(f"Loading thumbnail (LANCZOS upscale): {thumbnail_path}")
        img_array = np.array(
            Image.open(thumbnail_path).convert("RGB").resize((OUT_W, OUT_H), Image.LANCZOS)
        )

    # ── Ken Burns make_frame ──────────────────────────────────────────────────
    def make_frame(t):
        zoom = ZOOM_START + (ZOOM_END - ZOOM_START) * (t / duration)
        zw, zh = int(OUT_W * zoom), int(OUT_H * zoom)
        zoomed = Image.fromarray(img_array).resize((zw, zh), Image.BILINEAR)
        left   = max(0, (zw - OUT_W) // 2)
        top    = max(0, (zh - OUT_H) // 2)
        right  = min(zw, left + OUT_W)
        bottom = min(zh, top + OUT_H)
        frame  = np.array(zoomed.crop((left, top, right, bottom)))
        # Safety pad to exact OUT_W × OUT_H in case of rounding edge case
        if frame.shape[1] != OUT_W or frame.shape[0] != OUT_H:
            padded = np.zeros((OUT_H, OUT_W, 3), dtype=np.uint8)
            padded[:frame.shape[0], :frame.shape[1]] = frame
            return padded
        return frame

    # ── Build clip ────────────────────────────────────────────────────────────
    base = VideoClip(make_frame, duration=duration)
    base = set_fps(base, FPS)
    base = apply_fades(base)
    final = set_audio(base, audio)

    # ── Export ────────────────────────────────────────────────────────────────
    tmp_audio = os.path.join(tempfile.gettempdir(), "mpy_tmp_audio.mp4")
    logger.info(f"Rendering → {output_path}")

    write_kwargs = dict(
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        ffmpeg_params=["-crf", "23"],
        threads=4,
        temp_audiofile=tmp_audio,
        remove_temp=True,
        logger=None,
    )

    final.write_videofile(output_path, **write_kwargs)

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"  ✅ Done: {output_path} ({size_mb:.1f} MB, {duration:.1f}s)")

    audio.close()
    return output_path


def create_all_videos(
    scripts: dict,
    thumbnails: dict,
    audio_files: dict,
    output_dir: str = "output/videos",
) -> dict:
    from datetime import date
    today_str = date.today().isoformat()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = {}

    for state_key, data in scripts.items():
        thumb = thumbnails.get(state_key)
        audio = audio_files.get(state_key)
        if not thumb or not audio:
            logger.warning(f"Missing thumbnail or audio for {state_key}, skipping")
            continue
        out_path = f"{output_dir}/{state_key}_{today_str}.mp4"
        try:
            create_video(
                thumb, audio, out_path,
                data.get("price_data"),
                data.get("language", "hindi"),
                state_key=state_key,
            )
            results[state_key] = out_path
        except Exception as e:
            logger.error(f"Video creation failed for {state_key}: {e}")
            results[state_key] = None

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) == 4:
        create_video(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("Usage: python video_creator.py thumbnail.jpg audio.mp3 output.mp4")
