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
import shutil
import tempfile
import logging
import base64
import io
import subprocess
from html import escape
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

OUT_W, OUT_H = 1920, 1080
SHORT_W, SHORT_H = 1080, 1920
FPS = 24
FADE_IN  = 1.2
FADE_OUT = 1.5
ZOOM_START = 1.0
ZOOM_END   = 1.0    # no zoom — static image with fade in/out only
TREND_SEGMENT_SECONDS = 12
TREND_RENDER_FPS = 12


def create_avatar_video(image_path, audio_path, output_path, *, width, height):
    """Lip-synced talking-head video from a portrait image + audio (local SadTalker).

    Returns the output path on success, or None if SadTalker is unavailable/failed so
    the caller can fall back to the standard card video. The talking head is fitted to
    width×height with a blurred fill behind it (no ugly solid bars).
    """
    from avatar_sadtalker import render_talking_head

    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg not found; cannot compose avatar video.")
        return None

    with tempfile.TemporaryDirectory(prefix="avatar_") as work:
        raw = render_talking_head(image_path, audio_path, work)
        if not raw:
            return None
        # Scale-to-fit the talking head, fill the rest with a blurred copy of itself.
        vf = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"boxblur=24:6,crop={width}:{height}[bg];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", raw,
            "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-crf", "23", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            output_path,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except Exception as e:
            logger.error(f"Avatar compose (ffmpeg) failed to run ({e}); falling back.")
            return None
        if proc.returncode != 0:
            logger.error(f"Avatar compose ffmpeg exited {proc.returncode}; falling back.\n{proc.stderr[-600:]}")
            return None
    logger.info(f"  ✅ Avatar video: {output_path} ({width}×{height})")
    return output_path


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
    enable_trend_cards: bool = False,
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

    trend_context = (price_data or {}).get("history_context", {})
    trend_enabled = enable_trend_cards and _has_trend_series(trend_context)
    trend_duration = min(TREND_SEGMENT_SECONDS, max(0, duration - 1.0)) if trend_enabled else 0
    if trend_enabled:
        logger.info(f"Trend cards enabled for first {trend_duration:.1f}s")
    elif enable_trend_cards:
        logger.info("Trend cards requested, but not enough history is available")

    trend_cache: dict[int, np.ndarray] = {}
    trend_renderer = None
    if trend_enabled:
        try:
            trend_renderer = _BrowserTrendRenderer(img_array)
        except Exception as e:
            logger.warning(f"Browser trend-card renderer unavailable; skipping trend cards: {e}")
            trend_enabled = False
            trend_duration = 0

    # ── Ken Burns make_frame ──────────────────────────────────────────────────
    def make_frame(t):
        if trend_duration and trend_renderer and t < trend_duration:
            frame_key = int(t * TREND_RENDER_FPS)
            try:
                if frame_key not in trend_cache:
                    trend_cache[frame_key] = trend_renderer.render_frame(
                        price_data=price_data or {},
                        language=language,
                        state_key=state_key,
                        t=frame_key / TREND_RENDER_FPS,
                        duration=trend_duration,
                    )
                return trend_cache[frame_key]
            except Exception as e:
                logger.warning(f"Trend-card frame render failed; falling back to thumbnail frame: {e}")

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

    try:
        final.write_videofile(output_path, **write_kwargs)
    finally:
        if trend_renderer:
            trend_renderer.close()

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"  ✅ Done: {output_path} ({size_mb:.1f} MB, {duration:.1f}s)")

    audio.close()
    return output_path


def save_trend_preview(
    thumbnail_path: str,
    output_path: str,
    price_data: dict,
    language: str,
    state_key: str,
) -> str | None:
    """Save a representative trend-card frame for local review."""
    history_context = (price_data or {}).get("history_context", {})
    if not _has_trend_series(history_context):
        return None

    frame = np.array(Image.open(thumbnail_path).convert("RGB").resize((OUT_W, OUT_H), Image.LANCZOS))
    renderer = None
    try:
        renderer = _BrowserTrendRenderer(frame)
        preview = renderer.render_frame(
            price_data=price_data,
            language=language,
            state_key=state_key,
            t=TREND_SEGMENT_SECONDS * 0.72,
            duration=TREND_SEGMENT_SECONDS,
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(preview).save(output_path, "JPEG", quality=92)
        return output_path
    except Exception as e:
        logger.warning(f"Trend preview render skipped because browser text rendering failed: {e}")
        return None
    finally:
        if renderer:
            renderer.close()


def create_vertical_video(
    thumbnail_path: str,
    audio_path: str,
    output_path: str,
    vertical_frame_path: str | None = None,
) -> str:
    """
    Create a vertical 9:16 video suitable for Shorts/Reels from a frame + audio.

    Preferred: pass ``vertical_frame_path`` — a purpose-built portrait (1080×1920)
    template that fills the whole screen. If it is not provided, fall back to the
    legacy behaviour of blur-padding the horizontal ``thumbnail_path`` into a 9:16
    frame (which leaves the landscape card floating in the middle).
    """
    VideoClip, AudioFileClip, CompositeVideoClip, apply_fades, set_audio, set_fps, ver = _import_moviepy()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Loading audio for vertical video: {audio_path}")
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    logger.info(f"  Duration: {duration:.1f}s")

    if vertical_frame_path:
        logger.info(f"Using portrait template frame: {vertical_frame_path}")
        img_array = _load_vertical_template(vertical_frame_path)
    else:
        img_array = _build_vertical_frame(thumbnail_path)

    def make_frame(t):
        return img_array

    base = VideoClip(make_frame, duration=duration)
    base = set_fps(base, FPS)
    base = apply_fades(base)
    final = set_audio(base, audio)

    tmp_audio = os.path.join(tempfile.gettempdir(), "mpy_tmp_audio_vertical.mp4")
    logger.info(f"Rendering vertical video → {output_path}")
    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        ffmpeg_params=["-crf", "24"],
        threads=4,
        temp_audiofile=tmp_audio,
        remove_temp=True,
        logger=None,
    )

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f"  ✅ Done: {output_path} ({size_mb:.1f} MB, {duration:.1f}s)")
    audio.close()
    return output_path


def _load_vertical_template(frame_path: str) -> np.ndarray:
    """Load the portrait template and cover-fit it exactly to SHORT_W × SHORT_H."""
    img = Image.open(frame_path).convert("RGB")
    if img.size != (SHORT_W, SHORT_H):
        scale = max(SHORT_W / img.width, SHORT_H / img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        left = (img.width - SHORT_W) // 2
        top = (img.height - SHORT_H) // 2
        img = img.crop((left, top, left + SHORT_W, top + SHORT_H))
    return np.array(img)


def _build_vertical_frame(thumbnail_path: str) -> np.ndarray:
    source = Image.open(thumbnail_path).convert("RGB")

    # Cover-crop background to 9:16, then blur/dim it so foreground stays readable.
    bg_scale = max(SHORT_W / source.width, SHORT_H / source.height)
    bg_size = (int(source.width * bg_scale), int(source.height * bg_scale))
    background = source.resize(bg_size, Image.LANCZOS)
    left = (background.width - SHORT_W) // 2
    top = (background.height - SHORT_H) // 2
    background = background.crop((left, top, left + SHORT_W, top + SHORT_H))
    background = background.filter(ImageFilter.GaussianBlur(radius=22))
    background = ImageEnhance.Brightness(background).enhance(0.42)

    # Foreground keeps the original 16:9 card crisp and centered.
    fg_width = int(SHORT_W * 0.92)
    fg_height = int(fg_width * source.height / source.width)
    foreground = source.resize((fg_width, fg_height), Image.LANCZOS)
    x = (SHORT_W - fg_width) // 2
    y = int(SHORT_H * 0.19)

    canvas = background.convert("RGBA")
    shadow = Image.new("RGBA", (fg_width + 32, fg_height + 32), (0, 0, 0, 0))
    shadow_layer = Image.new("RGBA", (fg_width, fg_height), (0, 0, 0, 135))
    shadow.paste(shadow_layer, (16, 16))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
    canvas.alpha_composite(shadow, (x - 16, y - 16))
    canvas.paste(foreground.convert("RGBA"), (x, y))

    return np.array(canvas.convert("RGB"))


REGIONAL_VIDEO_LABELS = {
    "telugu": {
        "trend": "బంగారం ధరల ట్రెండ్",
        "today": "నేడు",
        "change": "మార్పు",
        "per_gram": "గ్రాముకు",
        "ten_grams": "10 గ్రాములు",
        "increased": "పెరిగింది",
        "decreased": "తగ్గింది",
        "unchanged": "మార్పు లేదు",
        "state_names": {"andhra_pradesh": "ఆంధ్రప్రదేశ్", "telangana": "తెలంగాణ"},
        "short_weekdays": ["సోమ", "మంగళ", "బుధ", "గురు", "శుక్ర", "శని", "నేడు"],
    },
    "tamil": {
        "trend": "தங்கம் விலை போக்கு",
        "today": "இன்று",
        "change": "மாற்றம்",
        "per_gram": "ஒரு கிராம்",
        "ten_grams": "10 கிராம்",
        "increased": "உயர்ந்தது",
        "decreased": "குறைந்தது",
        "unchanged": "மாற்றமில்லை",
        "state_names": {"tamil_nadu": "தமிழ்நாடு"},
        "short_weekdays": ["தி", "செ", "பு", "வி", "வெ", "ச", "இன்று"],
    },
    "hindi": {
        "trend": "सोने के भाव का रुझान",
        "today": "आज",
        "change": "बदलाव",
        "per_gram": "प्रति ग्राम",
        "ten_grams": "10 ग्राम",
        "increased": "बढ़ा",
        "decreased": "घटा",
        "unchanged": "स्थिर",
        "state_names": {"delhi": "दिल्ली"},
        "short_weekdays": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "आज"],
    },
}


def _has_trend_series(history_context: dict | None) -> bool:
    series = (history_context or {}).get("trend_series") or []
    return len(series) >= 2


class _BrowserTrendRenderer:
    """Render trend cards through Chromium so Indic text shaping matches thumbnails."""

    def __init__(self, thumbnail_frame: np.ndarray):
        from playwright.sync_api import sync_playwright

        self._bg_data_url = _frame_data_url(thumbnail_frame)
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        self._page = self._browser.new_page(viewport={"width": OUT_W, "height": OUT_H}, device_scale_factor=1)

    def render_frame(
        self,
        *,
        price_data: dict,
        language: str,
        state_key: str | None,
        t: float,
        duration: float,
    ) -> np.ndarray:
        html = _build_trend_html(
            bg_data_url=self._bg_data_url,
            price_data=price_data,
            language=language,
            state_key=state_key,
            t=t,
            duration=duration,
        )
        self._page.set_content(html, wait_until="domcontentloaded")
        self._page.wait_for_timeout(25)
        png = self._page.screenshot(
            type="jpeg",
            quality=92,
            clip={"x": 0, "y": 0, "width": OUT_W, "height": OUT_H},
        )
        return np.array(Image.open(io.BytesIO(png)).convert("RGB"))

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._playwright.stop()


def _build_trend_html(
    *,
    bg_data_url: str,
    price_data: dict,
    language: str,
    state_key: str | None,
    t: float,
    duration: float,
) -> str:
    labels = _regional_labels(language)
    series = price_data.get("history_context", {}).get("trend_series") or []
    cities = price_data.get("cities", {})
    primary_city = next(iter(cities), "")
    primary_prices = cities.get(primary_city, {})

    card_progress = _ease(min(1.0, t / 2.0))
    count_progress = _ease(min(1.0, max(0.0, (t - 1.0) / 2.4)))
    line_progress = _ease(min(1.0, max(0.0, (t - 3.2) / 4.6)))
    marker_progress = min(1.0, max(0.0, (t - 7.8) / max(1.0, duration - 7.8)))

    current_22 = float(primary_prices.get("22k_per_gram") or _last_series_value(series, "22k") or 0)
    current_24 = float(primary_prices.get("24k_per_gram") or _last_series_value(series, "24k") or 0)
    previous_22 = _previous_series_value(series, "22k", current_22)
    previous_24 = _previous_series_value(series, "24k", current_24)
    display_22 = previous_22 + (current_22 - previous_22) * count_progress
    display_24 = previous_24 + (current_24 - previous_24) * count_progress
    delta_22 = current_22 - previous_22
    delta_24 = current_24 - previous_24

    state_name = labels["state_names"].get(state_key or "", (state_key or "").replace("_", " ").title())
    city_name = _regional_city_name(language, primary_city)
    movement = _movement_label(labels, delta_24 or delta_22)
    regional_font = _regional_font_stack(language)
    title = f"{state_name} {labels['trend']}".strip()

    cards = [
        (_karat_label(language, "22k"), _price(display_22), _delta(delta_22), "#22c55e"),
        (_karat_label(language, "24k"), _price(display_24), _delta(delta_24), "#22c55e"),
        (city_name, _price(float(primary_prices.get("22k_per_10g") or current_22 * 10)), labels["ten_grams"], "#60a5fa"),
        (labels["change"], movement, labels["today"], "#f6c453"),
    ]
    card_html = "\n".join(
        _trend_card_html(label, value, footer, color, card_progress, idx)
        for idx, (label, value, footer, color) in enumerate(cards)
    )
    chart_svg = _trend_chart_svg(
        series=series,
        labels=labels,
        line_progress=line_progress,
        marker_progress=marker_progress,
    )

    return f"""<!DOCTYPE html>
<html lang="{escape(language)}">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    width: {OUT_W}px;
    height: {OUT_H}px;
    margin: 0;
    overflow: hidden;
    font-family: {regional_font}, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
    background: #111827;
    color: #f8fafc;
  }}
  .bg {{
    position: absolute;
    inset: 0;
    background:
      linear-gradient(120deg, rgba(17,24,39,.82), rgba(17,24,39,.72)),
      url("{bg_data_url}") center / cover no-repeat;
    filter: blur(14px) brightness(.55);
    transform: scale(1.04);
  }}
  .grid {{
    position: absolute;
    inset: 0;
    background-image: repeating-linear-gradient(74deg, rgba(59,130,246,.16) 0 1px, transparent 1px 96px);
    opacity: .34;
  }}
  .stage {{ position: relative; width: 100%; height: 100%; padding: 58px 90px; }}
  .title {{
    font-size: 74px;
    line-height: 1.08;
    font-weight: 700;
    color: #fff7db;
  }}
  .subtitle {{
    margin-top: 8px;
    font-size: 36px;
    color: #cbd5e1;
  }}
  .date {{
    position: absolute;
    right: 90px;
    top: 68px;
    width: 318px;
    height: 77px;
    border-radius: 26px;
    background: #f6c453;
    color: #1f2937;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 31px;
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
    font-weight: 700;
  }}
  .cards {{
    display: grid;
    grid-template-columns: 430px 430px 430px 345px;
    gap: 35px;
    margin-top: 38px;
  }}
  .card {{
    height: 232px;
    border-radius: 22px;
    background: rgba(31,41,55,.96);
    border: 2px solid rgba(71,85,105,.95);
    box-shadow: 0 18px 30px rgba(0,0,0,.35);
    padding: 31px 32px;
    transform: translateY(var(--offset));
    opacity: var(--opacity);
  }}
  .card-label {{
    font-size: 32px;
    color: #cbd5e1;
    line-height: 1.1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .card-value {{
    margin-top: 22px;
    font-size: 62px;
    line-height: 1;
    color: #ffffff;
    white-space: nowrap;
  }}
  .pill {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 204px;
    height: 46px;
    margin-top: 2px;
    border-radius: 19px;
    background: var(--accent);
    color: #111827;
    font-size: 27px;
    line-height: 1;
    padding: 0 26px;
  }}
  .chart {{
    margin-top: 62px;
    width: 1740px;
    height: 427px;
    border-radius: 24px;
    background: #0f172a;
    border: 2px solid #334155;
    box-shadow: 0 18px 30px rgba(0,0,0,.28);
    position: relative;
    overflow: hidden;
  }}
  .chart-title {{
    position: absolute;
    left: 34px;
    top: 29px;
    font-size: 42px;
    font-weight: 700;
  }}
  .legend {{
    position: absolute;
    right: 62px;
    top: 38px;
    height: 54px;
    border-radius: 18px;
    background: #1f2937;
    display: flex;
    align-items: center;
    gap: 28px;
    padding: 0 25px;
    font-size: 27px;
  }}
  .dot {{ width: 22px; height: 22px; border-radius: 50%; display: inline-block; margin-right: 10px; }}
  .footer {{
    position: absolute;
    left: 90px;
    bottom: 45px;
    font-size: 28px;
    color: #cbd5e1;
  }}
</style>
</head>
<body>
  <div class="bg"></div>
  <div class="grid"></div>
  <main class="stage">
    <div class="title">{escape(title)}</div>
    <div class="subtitle">{escape(labels['today'])} | 22K &amp; 24K {escape(labels['per_gram'])}</div>
    <div class="date">{escape(_display_date(price_data))}</div>
    <section class="cards">{card_html}</section>
    <section class="chart">
      <div class="chart-title">{escape(labels['trend'])}</div>
      <div class="legend">
        <span><span class="dot" style="background:#f59e0b"></span>24K</span>
        <span><span class="dot" style="background:#22c55e"></span>22K</span>
      </div>
      {chart_svg}
    </section>
    <div class="footer">{escape(_regional_footer(language))}</div>
  </main>
</body>
</html>"""


def _trend_card_html(label: str, value: str, footer: str, color: str, progress: float, index: int) -> str:
    offset = int((1 - progress) * (70 + index * 12))
    opacity = max(0.0, min(1.0, progress))
    return f"""<article class="card" style="--offset:{offset}px;--opacity:{opacity:.3f};--accent:{color}">
      <div class="card-label">{escape(label)}</div>
      <div class="card-value">{escape(value)}</div>
      <div class="pill">{escape(footer)}</div>
    </article>"""


def _trend_chart_svg(
    *,
    series: list[dict],
    labels: dict,
    line_progress: float,
    marker_progress: float,
) -> str:
    chart_x, chart_y, chart_w, chart_h = 85, 135, 1570, 230
    all_values = [float(row[k]) for row in series for k in ("22k", "24k") if row.get(k) is not None]
    if not all_values:
        return ""
    min_val = min(all_values) - 20
    max_val = max(all_values) + 20
    points_24 = _series_points(series, "24k", (chart_x, chart_y, chart_x + chart_w, chart_y + chart_h), min_val, max_val)
    points_22 = _series_points(series, "22k", (chart_x, chart_y, chart_x + chart_w, chart_y + chart_h), min_val, max_val)
    visible_24 = _visible_points(points_24, line_progress)
    visible_22 = _visible_points(points_22, line_progress)
    pulse = 1.0 + 0.24 * np.sin(marker_progress * np.pi * 6)
    marker_radius = max(0, int(22 * pulse)) if line_progress >= 0.98 and points_24 else 0
    marker = ""
    if marker_radius:
        x, y = points_24[-1]
        marker = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{marker_radius}" fill="none" stroke="#fff7db" stroke-width="5" />'

    grid = []
    for i in range(5):
        y = chart_y + i * chart_h / 4
        grid.append(f'<line x1="{chart_x}" y1="{y:.1f}" x2="{chart_x + chart_w}" y2="{y:.1f}" stroke="#1e293b" stroke-width="2" />')
    for i in range(max(1, len(series))):
        x = chart_x + i * chart_w / max(1, len(series) - 1)
        grid.append(f'<line x1="{x:.1f}" y1="{chart_y}" x2="{x:.1f}" y2="{chart_y + chart_h}" stroke="#172033" stroke-width="1" />')

    weekday_labels = labels.get("short_weekdays") or []
    x_labels = []
    for idx, row in enumerate(series):
        x = chart_x + idx * chart_w / max(1, len(series) - 1)
        if idx == len(series) - 1:
            label = labels["today"]
        elif len(series) <= len(weekday_labels):
            label = weekday_labels[idx]
        else:
            label = str(row.get("date", ""))[5:]
        x_labels.append(f'<text x="{x:.1f}" y="{chart_y + chart_h + 52}" text-anchor="middle" fill="#94a3b8" font-size="24">{escape(label)}</text>')

    circles = []
    for x, y in visible_24[:-1]:
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="#f59e0b" />')
    for x, y in visible_22[:-1]:
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="#22c55e" />')

    return f"""<svg width="1740" height="427" viewBox="0 0 1740 427" style="position:absolute;left:0;top:0">
      {''.join(grid)}
      <polyline points="{_points_attr(visible_24)}" fill="none" stroke="#f59e0b" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
      <polyline points="{_points_attr(visible_22)}" fill="none" stroke="#22c55e" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
      {''.join(circles)}
      {marker}
      {''.join(x_labels)}
    </svg>"""


def _visible_points(points: list[tuple[float, float]], progress: float) -> list[tuple[float, float]]:
    if len(points) < 2 or progress <= 0:
        return points[:1]
    max_segments = len(points) - 1
    exact_segments = progress * max_segments
    full_segments = int(exact_segments)
    partial = exact_segments - full_segments
    visible = points[: full_segments + 1]
    if full_segments < max_segments:
        x1, y1 = points[full_segments]
        x2, y2 = points[full_segments + 1]
        visible.append((x1 + (x2 - x1) * partial, y1 + (y2 - y1) * partial))
    return visible


def _points_attr(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _frame_data_url(frame: np.ndarray) -> str:
    image = Image.fromarray(frame).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _build_trend_frame(
    *,
    thumbnail_frame: np.ndarray,
    price_data: dict,
    language: str,
    state_key: str | None,
    t: float,
    duration: float,
) -> np.ndarray:
    labels = _regional_labels(language)
    series = price_data.get("history_context", {}).get("trend_series") or []
    cities = price_data.get("cities", {})
    primary_city = next(iter(cities), "")
    primary_prices = cities.get(primary_city, {})
    card_progress = _ease(min(1.0, t / 2.0))
    count_progress = _ease(min(1.0, max(0.0, (t - 1.0) / 2.4)))
    line_progress = _ease(min(1.0, max(0.0, (t - 3.2) / 4.6)))
    marker_progress = min(1.0, max(0.0, (t - 7.8) / max(1.0, duration - 7.8)))

    bg = Image.fromarray(thumbnail_frame).convert("RGB")
    bg = bg.filter(ImageFilter.GaussianBlur(radius=18))
    bg = ImageEnhance.Brightness(bg).enhance(0.24)
    overlay = Image.new("RGB", (OUT_W, OUT_H), "#111827")
    canvas = Image.blend(bg, overlay, 0.55).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    _draw_subtle_grid(draw)
    font = _font_loader(language)
    state_name = labels["state_names"].get(state_key or "", (state_key or "").replace("_", " ").title())
    title = f"{state_name} {labels['trend']}".strip()
    draw.text((90, 58), title, font=font(74), fill="#fff7db")
    draw.text((94, 145), f"{labels['today']} | 22K & 24K {labels['per_gram']}", font=font(36), fill="#cbd5e1")
    _draw_badge(draw, (1510, 68, 1828, 145), _display_date(price_data), font(31), "#f6c453", "#1f2937")

    current_22 = float(primary_prices.get("22k_per_gram") or _last_series_value(series, "22k") or 0)
    current_24 = float(primary_prices.get("24k_per_gram") or _last_series_value(series, "24k") or 0)
    previous_22 = _previous_series_value(series, "22k", current_22)
    previous_24 = _previous_series_value(series, "24k", current_24)
    display_22 = previous_22 + (current_22 - previous_22) * count_progress
    display_24 = previous_24 + (current_24 - previous_24) * count_progress
    delta_22 = current_22 - previous_22
    delta_24 = current_24 - previous_24
    movement = _movement_label(labels, delta_24 or delta_22)

    city_name = _regional_city_name(language, primary_city)
    cards = [
        ((90, 230, 520, 462), _karat_label(language, "22k"), _price(display_22), _delta(delta_22), "#22c55e"),
        ((555, 230, 985, 462), _karat_label(language, "24k"), _price(display_24), _delta(delta_24), "#22c55e"),
        ((1020, 230, 1450, 462), city_name, _price(float(primary_prices.get("22k_per_10g") or current_22 * 10)), labels["ten_grams"], "#60a5fa"),
        ((1485, 230, 1830, 462), labels["change"], movement, labels["today"], "#f6c453"),
    ]
    for idx, (box, label, value, footer, color) in enumerate(cards):
        _draw_price_card(canvas, box, label, value, footer, color, font, card_progress, idx)

    _draw_trend_chart(
        draw,
        font=font,
        labels=labels,
        series=series,
        box=(90, 525, 1830, 952),
        line_progress=line_progress,
        marker_progress=marker_progress,
    )

    draw.text(
        (90, 997),
        _regional_footer(language),
        font=font(28),
        fill="#cbd5e1",
    )
    return np.array(canvas.convert("RGB"))


def _draw_subtle_grid(draw: ImageDraw.ImageDraw) -> None:
    for x in range(-260, OUT_W, 96):
        draw.line((x, 0, x + 390, OUT_H), fill="#1e293b", width=1)


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    font,
    fill: str,
    text_fill: str,
) -> None:
    draw.rounded_rectangle(box, radius=26, fill=fill)
    x1, y1, x2, y2 = box
    draw.text(((x1 + x2) / 2, (y1 + y2) / 2 - 2), text, font=font, fill=text_fill, anchor="mm")


def _draw_price_card(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    footer: str,
    accent: str,
    font,
    progress: float,
    index: int,
) -> None:
    draw = ImageDraw.Draw(canvas)
    x1, y1, x2, y2 = box
    offset = int((1 - progress) * (70 + index * 12))
    y1 += offset
    y2 += offset

    shadow = Image.new("RGBA", (x2 - x1 + 30, y2 - y1 + 30), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((15, 15, x2 - x1 + 15, y2 - y1 + 15), radius=24, fill=(0, 0, 0, int(105 * progress)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    canvas.alpha_composite(shadow, (x1 - 15, y1 - 8))

    fill = (31, 41, 55, int(245 * progress))
    outline = (71, 85, 105, int(255 * progress))
    draw.rounded_rectangle((x1, y1, x2, y2), radius=22, fill=fill, outline=outline, width=2)
    draw.text((x1 + 32, y1 + 28), label, font=font(32), fill="#cbd5e1")
    draw.text((x1 + 32, y1 + 88), value, font=font(62), fill="#ffffff")
    draw.rounded_rectangle((x1 + 32, y2 - 74, x1 + 236, y2 - 28), radius=19, fill=accent)
    draw.text((x1 + 58, y2 - 66), footer, font=font(27), fill="#111827")


def _draw_trend_chart(
    draw: ImageDraw.ImageDraw,
    *,
    font,
    labels: dict,
    series: list[dict],
    box: tuple[int, int, int, int],
    line_progress: float,
    marker_progress: float,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=24, fill="#0f172a", outline="#334155", width=2)
    draw.text((x1 + 34, y1 + 30), labels["trend"], font=font(42), fill="#f8fafc")

    chart = (x1 + 85, y1 + 135, x2 - 85, y2 - 82)
    cx1, cy1, cx2, cy2 = chart
    for i in range(5):
        y = cy1 + i * (cy2 - cy1) / 4
        draw.line((cx1, y, cx2, y), fill="#1e293b", width=2)
    for i in range(max(1, len(series))):
        x = cx1 + i * (cx2 - cx1) / max(1, len(series) - 1)
        draw.line((x, cy1, x, cy2), fill="#172033", width=1)

    all_values = [float(row[k]) for row in series for k in ("22k", "24k") if row.get(k) is not None]
    if not all_values:
        return
    min_val = min(all_values) - 20
    max_val = max(all_values) + 20

    points_24 = _series_points(series, "24k", chart, min_val, max_val)
    points_22 = _series_points(series, "22k", chart, min_val, max_val)
    _draw_partial_line(draw, points_24, "#f59e0b", line_progress)
    _draw_partial_line(draw, points_22, "#22c55e", line_progress)

    if line_progress >= 0.98 and points_24:
        pulse = 1.0 + 0.24 * np.sin(marker_progress * np.pi * 6)
        radius = int(22 * pulse)
        x, y = points_24[-1]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="#fff7db", width=5)

    weekday_labels = labels.get("short_weekdays") or []
    for idx, row in enumerate(series):
        x = cx1 + idx * (cx2 - cx1) / max(1, len(series) - 1)
        if idx == len(series) - 1:
            label = labels["today"]
        elif len(series) <= len(weekday_labels):
            label = weekday_labels[idx]
        else:
            label = str(row.get("date", ""))[5:]
        draw.text((x - 24, cy2 + 22), label, font=font(24), fill="#94a3b8")

    legend_x = x2 - 310
    draw.rounded_rectangle((legend_x, y1 + 38, x2 - 62, y1 + 92), radius=18, fill="#1f2937")
    draw.ellipse((legend_x + 24, y1 + 58, legend_x + 46, y1 + 80), fill="#f59e0b")
    draw.text((legend_x + 60, y1 + 50), _karat_label_from_labels("24k"), font=font(27), fill="#e5e7eb")
    draw.ellipse((legend_x + 150, y1 + 58, legend_x + 172, y1 + 80), fill="#22c55e")
    draw.text((legend_x + 186, y1 + 50), _karat_label_from_labels("22k"), font=font(27), fill="#e5e7eb")


def _draw_partial_line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], color: str, progress: float) -> None:
    if len(points) < 2 or progress <= 0:
        return
    max_segments = len(points) - 1
    exact_segments = progress * max_segments
    full_segments = int(exact_segments)
    partial = exact_segments - full_segments
    visible = points[: full_segments + 1]
    if full_segments < max_segments:
        x1, y1 = points[full_segments]
        x2, y2 = points[full_segments + 1]
        visible.append((x1 + (x2 - x1) * partial, y1 + (y2 - y1) * partial))
    if len(visible) >= 2:
        draw.line(visible, fill=color, width=7, joint="curve")
    for x, y in visible[:-1]:
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color)


def _series_points(
    series: list[dict],
    karat: str,
    chart: tuple[int, int, int, int],
    min_val: float,
    max_val: float,
) -> list[tuple[float, float]]:
    cx1, cy1, cx2, cy2 = chart
    points = []
    value_range = max(1, max_val - min_val)
    for idx, row in enumerate(series):
        x = cx1 + idx * (cx2 - cx1) / max(1, len(series) - 1)
        y = cy2 - (float(row[karat]) - min_val) / value_range * (cy2 - cy1)
        points.append((x, y))
    return points


def _font_loader(language: str):
    regional_path = _font_path_for_language(language)
    latin_path = _first_existing(
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    )

    def load(size: int, *, latin: bool = False):
        path = latin_path if latin and latin_path else regional_path
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    return load


def _font_path_for_language(language: str) -> str | None:
    try:
        from thumbnail_generator import FONT_CANDIDATES, SYSTEM_FONT_FILES

        for font_name in FONT_CANDIDATES.get(language, FONT_CANDIDATES["hindi"]):
            path = _first_existing(*SYSTEM_FONT_FILES.get(font_name, []))
            if path:
                return path
    except Exception:
        pass
    return _first_existing("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _first_existing(*paths: str) -> str | None:
    for path in paths:
        if path and Path(path).exists():
            return path
    return None


def _regional_labels(language: str) -> dict:
    return REGIONAL_VIDEO_LABELS.get(language, REGIONAL_VIDEO_LABELS["hindi"])


def _regional_font_stack(language: str) -> str:
    try:
        from thumbnail_generator import LANG_STRINGS, _css_font_stack

        strings = LANG_STRINGS.get(language, LANG_STRINGS["hindi"])
        return _css_font_stack(strings["font"])
    except Exception:
        return "'Kohinoor Telugu', 'Telugu MN', 'Telugu Sangam MN', 'Noto Sans Telugu'"


def _karat_label(language: str, karat: str) -> str:
    try:
        from thumbnail_generator import LANG_STRINGS

        strings = LANG_STRINGS.get(language, LANG_STRINGS["hindi"])
        return strings["c22"] if karat == "22k" else strings["c24"]
    except Exception:
        return _karat_label_from_labels(karat)


def _karat_label_from_labels(karat: str) -> str:
    return "22K" if karat == "22k" else "24K"


def _regional_city_name(language: str, city: str) -> str:
    try:
        from thumbnail_generator import CITY_NAMES

        return CITY_NAMES.get(language, {}).get(city, city)
    except Exception:
        return city


def _regional_footer(language: str) -> str:
    footers = {
        "telugu": "గత ధరలు లేకపోతే ట్రెండ్ భాగం ఆటోమేటిక్‌గా స్కిప్ అవుతుంది.",
        "tamil": "முந்தைய தரவு இல்லையெனில் இந்த பகுதி தானாக தவிர்க்கப்படும்.",
        "hindi": "पुराना डेटा न हो तो यह ट्रेंड भाग अपने आप छोड़ दिया जाएगा.",
    }
    return footers.get(language, footers["hindi"])


def _display_date(price_data: dict) -> str:
    return str(price_data.get("date") or price_data.get("cached_date") or "")


def _price(value: float) -> str:
    return f"₹{int(round(value)):,}"


def _delta(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}₹{int(round(value))}"


def _movement_label(labels: dict, value: float) -> str:
    if value > 0:
        return labels["increased"]
    if value < 0:
        return labels["decreased"]
    return labels["unchanged"]


def _last_series_value(series: list[dict], karat: str) -> float | None:
    for row in reversed(series):
        if karat in row:
            return float(row[karat])
    return None


def _previous_series_value(series: list[dict], karat: str, fallback: float) -> float:
    if len(series) >= 2 and karat in series[-2]:
        return float(series[-2][karat])
    return fallback


def _ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1 - (1 - value) ** 3


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
