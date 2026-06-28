"""
modules/base.py — Content-module interface for the multi-show video platform.

Every "show" (gold prices, stock updates, horoscope, …) implements ContentModule.
The engine (main.py) calls only these methods and never references a specific domain,
so adding a new show is a new module + registry entry, not an engine change.

Tracker: PLAT-001 (interface), PLAT-007 (optional history via `needs_history`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Normalized validation outcome the engine can treat generically."""
    valid: bool
    details: dict                                     # machine-readable, stored in the run record
    errors: list[str] = field(default_factory=list)   # human-readable lines to log


class ContentModule(ABC):
    """Interface every content show implements.

    A "channel" is one content stream for the show (e.g. gold-in-Tamil-Nadu,
    NIFTY-in-Hindi, Aries-in-English). The engine drives the shared pipeline and
    delegates every domain-specific step to the module.
    """

    key: str = ""
    display_name: str = ""
    needs_history: bool = False

    # ── Channels ──────────────────────────────────────────────────────────────
    @abstractmethod
    def channels(self) -> list[str]:
        """Enabled channel keys for this show."""

    @abstractmethod
    def channel_meta(self, channel: str) -> dict:
        """Per-channel metadata (at least region_name, youtube_token_file)."""

    @abstractmethod
    def language_for(self, channel: str) -> str:
        """Language key used for script + voice + template."""

    # ── Data ──────────────────────────────────────────────────────────────────
    @abstractmethod
    def fetch(self, channel: str) -> dict:
        """Acquire today's raw data (scrape / API / compute)."""

    @abstractmethod
    def validate(self, data: dict) -> ValidationResult:
        """Validate fetched data before anything downstream runs."""

    def build_history(self, channel: str, data: dict, run_date: str) -> dict:
        """Persist today's data and return a history/comparison context.

        Only invoked when ``needs_history`` is True. Stateless shows (e.g. horoscope)
        leave this as a no-op.
        """
        return {}

    # ── Script ────────────────────────────────────────────────────────────────
    @abstractmethod
    def generate_script(self, channel: str, data: dict) -> str:
        """Long-form (~75-110s) script in the channel's language."""

    @abstractmethod
    def generate_short_script(self, channel: str, data: dict) -> str:
        """Ultra-short (~30s) script for Shorts/Reels."""

    # ── Visuals ───────────────────────────────────────────────────────────────
    @abstractmethod
    def render_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        """Landscape 16:9 template/thumbnail."""

    @abstractmethod
    def render_vertical_thumbnail(self, channel: str, data: dict, output_path: str) -> str:
        """Portrait 9:16 template for Shorts/Reels."""

    # ── Publish ───────────────────────────────────────────────────────────────
    @abstractmethod
    def youtube_metadata(self, channel: str, privacy_status: str) -> dict:
        """Title/description/tags payload for upload + review."""

    # ── Preflight (optional) ──────────────────────────────────────────────────
    def preflight(self, channels: list[str]) -> bool:
        """Optional pre-run checks (fonts, credentials, …). Return False to abort."""
        return True


REGISTRY: dict[str, "ContentModule"] = {}


def register(module: "ContentModule") -> None:
    REGISTRY[module.key] = module


def get_module(key: str) -> "ContentModule":
    if key not in REGISTRY:
        available = ", ".join(sorted(REGISTRY)) or "none"
        raise KeyError(f"Unknown content module '{key}'. Available: {available}")
    return REGISTRY[key]
