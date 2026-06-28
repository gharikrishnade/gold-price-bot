"""
modules/gold.py — Gold-price content module.

Adapter that wraps the existing gold-specific code (scraper, validator, history,
script/thumbnail generators, YouTube metadata) behind the ContentModule interface.
The underlying functions are unchanged, preserving exact gold behavior.

Tracker: PLAT-002 (extract gold), MOD-GOLD-001 (parity).
"""
from __future__ import annotations

import logging

from config import CHANNEL_CONFIG
from scraper import get_state_prices
from price_validator import validate_state_price_data
from price_history import build_history_context, store_price_data
from script_generator import generate_script, generate_short_script
from thumbnail_generator import (
    check_required_fonts,
    generate_thumbnail,
    generate_vertical_thumbnail,
)
from youtube_uploader import build_video_metadata

from modules.base import ContentModule, ValidationResult

logger = logging.getLogger("modules.gold")


class GoldModule(ContentModule):
    key = "gold"
    display_name = "Gold Price Updates"
    needs_history = True

    # ── Channels ──────────────────────────────────────────────────────────────
    def channels(self) -> list[str]:
        return [k for k, c in CHANNEL_CONFIG.items() if c.get("enabled", True)]

    def channel_meta(self, channel: str) -> dict:
        return CHANNEL_CONFIG[channel]

    def language_for(self, channel: str) -> str:
        return CHANNEL_CONFIG[channel]["language"]

    # ── Data ──────────────────────────────────────────────────────────────────
    def fetch(self, channel: str) -> dict:
        return get_state_prices(channel)

    def validate(self, data: dict) -> ValidationResult:
        result = validate_state_price_data(data)
        errors = [
            f"{city.city}: {'; '.join(city.errors)}"
            for city in result.city_results
            if not city.valid
        ]
        return ValidationResult(valid=result.valid, details=result.to_dict(), errors=errors)

    def build_history(self, channel: str, data: dict, run_date: str) -> dict:
        context = build_history_context(channel, data, run_date=run_date)
        data["history_context"] = context
        store_price_data(channel, data, run_date=run_date)
        return context

    # ── Script ────────────────────────────────────────────────────────────────
    def generate_script(self, channel: str, data: dict) -> str:
        return generate_script(self.language_for(channel), channel, data)

    def generate_short_script(self, channel: str, data: dict) -> str:
        return generate_short_script(self.language_for(channel), channel, data)

    # ── Visuals ───────────────────────────────────────────────────────────────
    def render_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        return generate_thumbnail(self.language_for(channel), channel, data, output_path)

    def render_vertical_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        return generate_vertical_thumbnail(self.language_for(channel), channel, data, output_path)

    # ── Publish ───────────────────────────────────────────────────────────────
    def youtube_metadata(self, channel: str, privacy_status: str) -> dict:
        return build_video_metadata(
            language=self.language_for(channel),
            state_key=channel,
            privacy_status=privacy_status,
        )

    # ── Preflight ─────────────────────────────────────────────────────────────
    def preflight(self, channels: list[str]) -> bool:
        languages = [self.language_for(c) for c in channels]
        font_results = check_required_fonts(languages)
        missing = {lang: r for lang, r in font_results.items() if not r["ok"]}
        if not missing:
            for lang, r in font_results.items():
                logger.info(f"Thumbnail font preflight OK for {lang}: {', '.join(r['installed'])}")
            return True
        for lang, r in missing.items():
            logger.error(
                f"Missing thumbnail font for {lang}. Install one of: {', '.join(r['required_any_of'])}"
            )
        return False
