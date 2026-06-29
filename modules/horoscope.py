"""
modules/horoscope.py — Daily horoscope content module.

The first stateless show: no external data and no history (`needs_history=False`).
Each channel is one zodiac sign. Daily "highlights" (lucky number / colour / mood)
are derived deterministically from (sign, date) so they are stable for the day
without an extra API call; the spoken reading itself is LLM-generated via the shared
script engine. Visuals use a devotional, symbol-rich card (zodiac glyph + Om motif +
temple-gold frame) with regional-language text, rendered via the shared template kit's
Chromium primitive.

Content safety (MOD-HORO-002): readings stay positive and general, avoid guaranteed
predictions, and every script states an "entertainment only" disclaimer.

Tracker: MOD-HORO-001 (module, 12 signs, stateless), MOD-HORO-002 (content-safety framing).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date
from html import escape

from jobs_config import jobs_for_module
from script_engine import LANGUAGE_META, ScriptBrief, generate as _engine_generate
from template_kit import Brand, render_html_to_image, css_font_stack
from youtube_uploader import _yt_language_code
from thumbnail_generator import FONT_CANDIDATES, ensure_language_font

from modules.base import ContentModule, ValidationResult

logger = logging.getLogger("modules.horoscope")

# Zodiac sign -> (display name, astrological glyph, date range).
ZODIAC = {
    "aries":       ("Aries",       "♈", "Mar 21 – Apr 19"),
    "taurus":      ("Taurus",      "♉", "Apr 20 – May 20"),
    "gemini":      ("Gemini",      "♊", "May 21 – Jun 20"),
    "cancer":      ("Cancer",      "♋", "Jun 21 – Jul 22"),
    "leo":         ("Leo",         "♌", "Jul 23 – Aug 22"),
    "virgo":       ("Virgo",       "♍", "Aug 23 – Sep 22"),
    "libra":       ("Libra",       "♎", "Sep 23 – Oct 22"),
    "scorpio":     ("Scorpio",     "♏", "Oct 23 – Nov 21"),
    "sagittarius": ("Sagittarius", "♐", "Nov 22 – Dec 21"),
    "capricorn":   ("Capricorn",   "♑", "Dec 22 – Jan 19"),
    "aquarius":    ("Aquarius",    "♒", "Jan 20 – Feb 18"),
    "pisces":      ("Pisces",      "♓", "Feb 19 – Mar 20"),
}


def _sign(channel: str) -> tuple[str, str, str]:
    return ZODIAC.get(channel, (channel.title(), "✷", ""))

_COLORS = ["Red", "Blue", "Green", "Gold", "Purple", "Silver", "Orange", "Teal", "Pink", "White"]
_MOODS = ["Bright", "Calm", "Energetic", "Focused", "Hopeful", "Cheerful", "Confident", "Balanced"]

# Devotional brand: deep maroon / saffron / temple-gold (TMPL-002).
HOROSCOPE_BRAND = Brand(
    key="horoscope", wordmark="दैनिक राशिफल", emblem="ॐ",
    bg="#1b0707", panel="#3a1410", panel_border="#7d5320",
    accent="#f4c542", accent_2="#ff8c2b", accent_3="#ffdf9e",
    text="#fff3df", text_muted="#d9b487",
)

# Per-language localization of the on-card text. Falls back to English.
_LOCALE = {
    "hindi": {
        "title": "॥ दैनिक राशिफल ॥", "rashi": "राशि",
        "lucky_number": "शुभ अंक", "mood": "आज का भाव", "lucky_color": "शुभ रंग",
        "disclaimer": "केवल मनोरंजन के लिए", "blessing": "॥ शुभ दिन ॥",
        "signs": {"aries": "मेष", "taurus": "वृषभ", "gemini": "मिथुन", "cancer": "कर्क",
                   "leo": "सिंह", "virgo": "कन्या", "libra": "तुला", "scorpio": "वृश्चिक",
                   "sagittarius": "धनु", "capricorn": "मकर", "aquarius": "कुम्भ", "pisces": "मीन"},
        "colors": {"Red": "लाल", "Blue": "नीला", "Green": "हरा", "Gold": "सुनहरा", "Purple": "बैंगनी",
                    "Silver": "रजत", "Orange": "नारंगी", "Teal": "फ़िरोज़ा", "Pink": "गुलाबी", "White": "श्वेत"},
        "moods": {"Bright": "उत्साह", "Calm": "शांति", "Energetic": "ऊर्जा", "Focused": "एकाग्रता",
                   "Hopeful": "आशा", "Cheerful": "प्रसन्नता", "Confident": "आत्मविश्वास", "Balanced": "संतुलन"},
    },
}


def _locale(language: str) -> dict:
    if language in _LOCALE:
        return _LOCALE[language]
    return {  # English fallback
        "title": "Daily Horoscope", "rashi": "",
        "lucky_number": "Lucky Number", "mood": "Mood", "lucky_color": "Lucky Colour",
        "disclaimer": "For entertainment only", "blessing": "Have a blessed day",
        "signs": {k: v[0] for k, v in ZODIAC.items()},
        "colors": {c: c for c in _COLORS}, "moods": {m: m for m in _MOODS},
    }

_DISCLAIMER = (
    "Clearly say, in one short friendly line, that this horoscope is only for entertainment "
    "and is not a real prediction or professional advice."
)


def _daily_highlights(sign: str, iso_date: str) -> tuple[int, str, str]:
    """Stable per-day lucky number / colour / mood derived from (sign, date)."""
    h = int(hashlib.sha256(f"{sign}:{iso_date}".encode()).hexdigest(), 16)
    lucky_number = (h % 9) + 1
    color = _COLORS[(h // 9) % len(_COLORS)]
    mood = _MOODS[(h // 900) % len(_MOODS)]
    return lucky_number, color, mood


def _devotional_card_html(data: dict, language: str, fmt: str, width: int, height: int) -> str:
    """Devotional, symbol-rich, regional-language horoscope card (landscape/portrait)."""
    L = _locale(language)
    sign = data["sign"]
    glyph = data.get("glyph", "✷")
    sign_name = L["signs"].get(sign, data.get("sign_display", sign.title()))
    num = str(data["lucky_number"])
    val_mood = L["moods"].get(data["mood"], data["mood"])
    val_color = L["colors"].get(data["lucky_color"], data["lucky_color"])
    date_str = data["date"]

    base = 1080 if fmt == "portrait" else 1280
    sc = width / base
    def px(v): return round(v * sc)
    portrait = fmt == "portrait"

    b = HOROSCOPE_BRAND
    reg = css_font_stack(",".join(FONT_CANDIDATES.get(language, FONT_CANDIDATES.get("hindi", ["Noto Sans Devanagari"]))))
    glyph_font = "'Apple Symbols','Arial Unicode MS','Segoe UI Symbol',sans-serif"

    med = px(380 if portrait else 196)
    glyph_sz = px(210 if portrait else 104)
    name_sz = px(88 if portrait else 52)
    om_sz = px(62 if portrait else 40)
    title_sz = px(46 if portrait else 30)
    chip_v = px(52 if portrait else 36)
    chip_l = px(28 if portrait else 22)
    pad = px(70 if portrait else 36)
    name_mt = px(18 if portrait else 8)
    date_mt = px(14 if portrait else 6)
    chips_mt = px(30 if portrait else 12)
    chip_pad = px(18 if portrait else 11)
    rashi_html = f' <span class="rashi">{escape(L["rashi"])}</span>' if L["rashi"] else ""

    chips = [(L["lucky_number"], num), (L["mood"], val_mood), (L["lucky_color"], val_color)]
    chips_html = "".join(
        f'<div class="chip"><div class="chip-l">{escape(c[0])}</div><div class="chip-v">{escape(c[1])}</div></div>'
        for c in chips
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body{{width:{width}px;height:{height}px;overflow:hidden;}}
  body{{background:radial-gradient(circle at 50% 30%, #5e1d14 0%, {b.bg} 60%, #110404 100%);
    color:{b.text}; font-family:{reg}; display:flex; flex-direction:column; align-items:center;
    padding:{pad}px; position:relative;}}
  .frame{{position:absolute; inset:{px(22)}px; border:{px(3)}px solid {b.accent}; border-radius:{px(30)}px;
    box-shadow:inset 0 0 0 {px(2)}px rgba(255,223,158,.25), inset 0 0 {px(70)}px rgba(0,0,0,.55); pointer-events:none;}}
  .corner{{position:absolute; color:{b.accent}; font-size:{px(32)}px; opacity:.85;}}
  .top{{display:flex; flex-direction:column; align-items:center;}}
  .om{{font-size:{om_sz}px; color:{b.accent}; line-height:1; text-shadow:0 0 {px(20)}px rgba(244,197,66,.55);}}
  .title{{font-size:{title_sz}px; color:{b.accent}; font-weight:700; letter-spacing:{px(2)}px; margin-top:{px(8)}px;}}
  .mid{{margin-top:auto; display:flex; flex-direction:column; align-items:center; width:100%;}}
  .medallion{{width:{med}px; height:{med}px; border-radius:50%;
    background:radial-gradient(circle at 50% 38%, #ffc170 0%, #d8731e 55%, #8a3d10 100%);
    border:{px(6)}px solid {b.accent};
    box-shadow:0 0 {px(44)}px rgba(244,197,66,.45), inset 0 0 {px(34)}px rgba(0,0,0,.4);
    display:flex; align-items:center; justify-content:center;}}
  .glyph{{font-family:{glyph_font}; font-size:{glyph_sz}px; color:#3a1606; line-height:1;}}
  .signname{{font-size:{name_sz}px; font-weight:800; color:{b.text}; margin-top:{name_mt}px;
    text-shadow:0 {px(2)}px {px(12)}px rgba(0,0,0,.5);}}
  .rashi{{font-size:{px(34 if portrait else 26)}px; color:{b.accent}; font-weight:600;}}
  .date{{margin-top:{date_mt}px; border:{px(2)}px solid {b.panel_border}; background:rgba(0,0,0,.3);
    border-radius:{px(40)}px; padding:{px(8)}px {px(26)}px; font-size:{px(28 if portrait else 24)}px; color:{b.accent};}}
  .chips{{display:flex; gap:{px(20)}px; margin-top:{chips_mt}px; width:100%; justify-content:center;}}
  .chip{{flex:1; max-width:{px(330)}px; background:rgba(0,0,0,.34); border:{px(2)}px solid {b.accent};
    border-radius:{px(18)}px; padding:{chip_pad}px {px(10)}px; text-align:center;}}
  .chip-l{{font-size:{chip_l}px; color:{b.accent_2}; font-weight:700;}}
  .chip-v{{font-size:{chip_v}px; color:{b.text}; font-weight:800; margin-top:{px(8)}px;}}
  .foot{{margin-top:auto; text-align:center;}}
  .blessing{{font-size:{px(42 if portrait else 30)}px; color:{b.accent}; font-weight:700;}}
  .disclaimer{{font-size:{px(24 if portrait else 20)}px; color:{b.text_muted}; margin-top:{px(6)}px;}}
</style></head><body>
  <div class="frame"></div>
  <div class="corner" style="top:{px(32)}px;left:{px(38)}px;">✦</div>
  <div class="corner" style="top:{px(32)}px;right:{px(38)}px;">✦</div>
  <div class="corner" style="bottom:{px(32)}px;left:{px(38)}px;">✦</div>
  <div class="corner" style="bottom:{px(32)}px;right:{px(38)}px;">✦</div>
  <div class="top"><div class="om">ॐ</div><div class="title">{escape(L["title"])}</div></div>
  <div class="mid">
    <div class="medallion"><div class="glyph">{glyph}</div></div>
    <div class="signname">{escape(sign_name)}{rashi_html}</div>
    <div class="date">{escape(date_str)}</div>
    <div class="chips">{chips_html}</div>
  </div>
  <div class="foot">
    <div class="blessing">{escape(L["blessing"])}</div>
    <div class="disclaimer">{escape(L["disclaimer"])}</div>
  </div>
</body></html>"""


class HoroscopeModule(ContentModule):
    key = "horoscope"
    display_name = "Daily Horoscope"
    needs_history = False

    # ── Channels ──────────────────────────────────────────────────────────────
    def _jobs(self) -> dict:
        return {j.channel: j for j in jobs_for_module("horoscope", enabled_only=False)}

    def channels(self) -> list[str]:
        return [j.channel for j in jobs_for_module("horoscope")]

    def channel_meta(self, channel: str) -> dict:
        job = self._jobs().get(channel)
        if job is None:
            raise KeyError(f"Unknown horoscope channel '{channel}'")
        return {
            "region_name": _sign(channel)[0],
            "language": job.language,
            "youtube_token_file": job.youtube_token_file,
            "channel_id": job.channel_id,
            "enabled": job.enabled,
        }

    def language_for(self, channel: str) -> str:
        return self.channel_meta(channel)["language"]

    # ── Data ──────────────────────────────────────────────────────────────────
    def fetch(self, channel: str) -> dict:
        today = date.today()
        n, color, mood = _daily_highlights(channel, today.isoformat())
        display, glyph, date_range = _sign(channel)
        return {
            "sign": channel,
            "sign_display": display,
            "glyph": glyph,
            "date_range": date_range,
            "date": today.strftime("%d %b %Y"),
            "lucky_number": n,
            "lucky_color": color,
            "mood": mood,
        }

    def validate(self, data: dict) -> ValidationResult:
        sign = data.get("sign")
        if sign not in ZODIAC:
            return ValidationResult(False, {"sign": sign}, [f"Unknown zodiac sign '{sign}'"])
        return ValidationResult(True, {"sign": sign, "lucky_number": data.get("lucky_number")}, [])

    # ── Script ────────────────────────────────────────────────────────────────
    def generate_script(self, channel: str, data: dict) -> str:
        return _engine_generate(self.language_for(channel), self._brief(data, "long"), variant="long")

    def generate_short_script(self, channel: str, data: dict) -> str:
        return _engine_generate(self.language_for(channel), self._brief(data, "short"), variant="short")

    def _brief(self, data: dict, variant: str) -> ScriptBrief:
        disp, n, color, mood = data["sign_display"], data["lucky_number"], data["lucky_color"], data["mood"]
        data_block = (
            f"Zodiac sign: {disp} ({data['date_range']})\n"
            f"Date: {data['date']}\n"
            f"Lucky number: {n}\nLucky colour: {color}\nMood today: {mood}"
        )
        if variant == "long":
            instructions = [
                f"Say this is today's horoscope for {disp}.",
                "Give a warm, encouraging reading in 4-6 short sentences covering general themes — "
                "overall mood, work or studies, relationships, and a simple wellness tip. Keep it positive and GENERAL.",
                f"Naturally mention the lucky number ({n}), lucky colour ({color}), and the mood ({mood}).",
                "Do NOT make specific or guaranteed predictions about health, money, marriage, or exam results.",
            ]
        else:
            instructions = [
                f"Say this is today's horoscope for {disp}.",
                f"Give 2-3 short, upbeat lines of general guidance, and mention the lucky number ({n}) and lucky colour ({color}).",
                "Do NOT make specific or guaranteed predictions.",
            ]
        return ScriptBrief(
            topic=f"today's horoscope for {disp}",
            data_block=data_block,
            instructions=instructions,
            disclaimers=[_DISCLAIMER],
        )

    # ── Visuals (devotional, symbol-rich, localized) ──────────────────────────
    def render_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        return self._render(channel, data, output_path, "landscape", 1280, 720)

    def render_vertical_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        return self._render(channel, data, output_path, "portrait", 1080, 1920)

    def _render(self, channel, data, output_path, fmt, w, h) -> str:
        language = self.language_for(channel)
        try:
            ensure_language_font(language)
        except Exception as e:
            logger.warning(f"Horoscope font check for {language}: {e}")
        html = _devotional_card_html(data, language, fmt, w, h)
        return render_html_to_image(html, output_path, w, h)

    # ── Publish ───────────────────────────────────────────────────────────────
    def youtube_metadata(self, channel: str, privacy_status: str) -> dict:
        disp = _sign(channel)[0]
        return {
            "title": f"{disp} Horoscope Today | Daily Astrology"[:100],
            "description": (
                f"Today's horoscope for {disp}.\n\n"
                "Disclaimer: This horoscope is for entertainment purposes only and is not a "
                "prediction or professional advice."
            ),
            "tags": ["horoscope", "daily horoscope", disp.lower(), "astrology", "zodiac", "rashifal"],
            "category_id": "24",  # Entertainment
            "default_language": _yt_language_code(self.language_for(channel)),
            "privacy_status": privacy_status,
            "self_declared_made_for_kids": False,
        }

    # ── Preflight ─────────────────────────────────────────────────────────────
    def preflight(self, channels: list[str]) -> bool:
        ok = True
        for c in channels:
            lang = self.language_for(c)
            if lang not in LANGUAGE_META:
                logger.error(f"Horoscope channel '{c}': unsupported language '{lang}'.")
                ok = False
        return ok
