"""
modules/horoscope.py — Daily horoscope content module.

The first stateless show: no external data and no history (`needs_history=False`).
Each channel is one zodiac sign. Daily "highlights" (lucky number / colour / mood)
are derived deterministically from (sign, date) so they are stable for the day
without an extra API call; the spoken reading itself is LLM-generated via the shared
script engine. Visuals are composed from the shared template kit with a distinct brand.

Content safety (MOD-HORO-002): readings stay positive and general, avoid guaranteed
predictions, and every script states an "entertainment only" disclaimer.

Tracker: MOD-HORO-001 (module, 12 signs, stateless), MOD-HORO-002 (content-safety framing).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date

from jobs_config import jobs_for_module
from script_engine import LANGUAGE_META, ScriptBrief, generate as _engine_generate
from template_kit import Brand, CardContent, StatCard, render_card
from youtube_uploader import _yt_language_code

from modules.base import ContentModule, ValidationResult

logger = logging.getLogger("modules.horoscope")

# Zodiac sign -> (display name, date range).
ZODIAC = {
    "aries":       ("Aries",       "Mar 21 – Apr 19"),
    "taurus":      ("Taurus",      "Apr 20 – May 20"),
    "gemini":      ("Gemini",      "May 21 – Jun 20"),
    "cancer":      ("Cancer",      "Jun 21 – Jul 22"),
    "leo":         ("Leo",         "Jul 23 – Aug 22"),
    "virgo":       ("Virgo",       "Aug 23 – Sep 22"),
    "libra":       ("Libra",       "Sep 23 – Oct 22"),
    "scorpio":     ("Scorpio",     "Oct 23 – Nov 21"),
    "sagittarius": ("Sagittarius", "Nov 22 – Dec 21"),
    "capricorn":   ("Capricorn",   "Dec 22 – Jan 19"),
    "aquarius":    ("Aquarius",    "Jan 20 – Feb 18"),
    "pisces":      ("Pisces",      "Feb 19 – Mar 20"),
}

_COLORS = ["Red", "Blue", "Green", "Gold", "Purple", "Silver", "Orange", "Teal", "Pink", "White"]
_MOODS = ["Bright", "Calm", "Energetic", "Focused", "Hopeful", "Cheerful", "Confident", "Balanced"]

# Distinct brand: deep violet / starlit, gold accent (TMPL-002).
HOROSCOPE_BRAND = Brand(
    key="horoscope", wordmark="DAILY HOROSCOPE", emblem="★",
    bg="#160a2b", panel="#241046", panel_border="#3b2566",
    accent="#e6c34d", accent_2="#a78bfa", accent_3="#f472b6",
)

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
            "region_name": ZODIAC.get(channel, (channel.title(), ""))[0],
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
        display, date_range = ZODIAC.get(channel, (channel.title(), ""))
        return {
            "sign": channel,
            "sign_display": display,
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

    # ── Visuals (shared template kit) ─────────────────────────────────────────
    def render_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        return render_card(HOROSCOPE_BRAND, self._card(data), output_path, fmt="landscape")

    def render_vertical_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        return render_card(HOROSCOPE_BRAND, self._card(data), output_path, fmt="portrait")

    def _card(self, data: dict) -> CardContent:
        return CardContent(
            title=f"{data['sign_display']} Today",
            subtitle=f"Daily Horoscope · {data['date_range']}",
            date_str=data["date"],
            stats=[
                StatCard("LUCKY NUMBER", str(data["lucky_number"])),
                StatCard("MOOD", data["mood"]),
                StatCard("LUCKY COLOUR", data["lucky_color"]),
            ],
            footer_text="For entertainment only",
        )

    # ── Publish ───────────────────────────────────────────────────────────────
    def youtube_metadata(self, channel: str, privacy_status: str) -> dict:
        disp = ZODIAC.get(channel, (channel.title(), ""))[0]
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
