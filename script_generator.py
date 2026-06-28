"""
script_generator.py — Gold-price script builder.

Builds gold-specific ScriptBriefs (the rates, city-grouping/comparison logic, and
gold vocabulary rules) and hands them to the shared, domain-agnostic
``script_engine`` which applies the host persona, tone, regional-language rules,
and call-to-action. The shared voice now lives in script_engine; this module owns
only the gold facts.

Tracker: PLAT-004 (shared script engine) — gold consumer.
"""

import logging
from config import CHANNEL_CONFIG
from script_engine import LANGUAGE_META, ScriptBrief, generate as _engine_generate

logger = logging.getLogger(__name__)

# Gold vocabulary rules (currency / weight unit / carat), shared by long + short briefs.
def _gold_vocabulary_rules(meta: dict) -> list[str]:
    name = meta["name"]
    return [
        f'- For the currency, write the {name} word "{meta["currency"]}" — do NOT use the "₹" symbol '
        f'or the English word "rupees" (a TTS voice reads "₹" in English).',
        f'- For the weight unit, write the {name} word "{meta["unit"]}" for one gram, and the {name} '
        f'phrase for "10 {meta["unit"]}" for ten grams. Do NOT use the English words "gram", "grams", "g", or "10g".',
        f'- Karats: always SPELL OUT the carat word in {name} (e.g. write the {name} equivalent of '
        f'"22 carat" / "24 carat"). You may keep the digits 22 and 24, but NEVER use the Latin letter '
        f'"K" (as in "22K") — a TTS voice mispronounces it.',
    ]


def generate_script(language: str, state_key: str, price_data: dict) -> str:
    """Generate a ~75-110s gold-price script via the shared script engine."""
    brief = _gold_long_brief(language, state_key, price_data)
    return _engine_generate(language, brief, variant="long")


def generate_short_script(language: str, state_key: str, price_data: dict) -> str:
    """Generate a ~30s gold-price Shorts/Reels script via the shared script engine."""
    brief = _gold_short_brief(language, state_key, price_data)
    return _engine_generate(language, brief, variant="short")


def _gold_long_brief(language: str, state_key: str, price_data: dict) -> ScriptBrief:
    meta = LANGUAGE_META[language]
    config = CHANNEL_CONFIG[state_key]
    date_str = price_data.get("date", "today")

    city_lines = []
    for city, prices in price_data.get("cities", {}).items():
        if prices:
            g22 = prices.get("22k_per_gram", 0)
            g24 = prices.get("24k_per_gram", 0)
            g22_10 = prices.get("22k_per_10g", 0)
            g24_10 = prices.get("24k_per_10g", 0)
            city_lines.append(
                f"- {city}: 22K = ₹{g22}/gram (₹{g22_10}/10g), 24K = ₹{g24}/gram (₹{g24_10}/10g)"
            )
    city_price_text = "\n".join(city_lines) if city_lines else "Prices unavailable today"

    is_cached = price_data.get("cached", False)
    cached_date = price_data.get("cached_date", "")
    data_note = (
        f"NOTE: Today is a market holiday. These are the LAST CLOSING PRICES from {cached_date}. "
        f"The script should briefly mention that the market is closed today and these are yesterday's / last session's closing rates."
        if is_cached else
        "These are today's live prices."
    )
    comparison_note = _format_history_context(price_data.get("history_context", {}))

    data_block = (
        f"Date: {date_str}\n"
        f"State/Region: {config['region_name']}\n"
        f"City-wise Gold Rates:\n{city_price_text}\n\n"
        f'(The data above uses the "₹" symbol and the English words "gram"/"10g" only for brevity. '
        f"In your spoken script you MUST NOT use them — see the LANGUAGE rules.)\n\n"
        f"DATA NOTE: {data_note}\n\n"
        f"COMPARISON DATA:\n{comparison_note}"
    )

    instructions = [
        "State the date clearly.",
        "If it's a market holiday, briefly say so and mention these are last closing prices.",
        "Announce the gold rates naturally (22K and 24K, both per gram and per 10 grams).\n"
        "   - IMPORTANT: Do NOT recite the same rates city by city if they are identical. First check the data: "
        "if two or more cities share the EXACT same 22K and 24K rates, GROUP them and state the rate ONCE for all "
        'of them together (e.g. "in Vijayawada, Visakhapatnam and Guntur the rate is the same today — ..."). Only '
        "call out a city separately when its rate actually differs from the others.\n"
        "   - Repeating the same numbers three times in a row makes viewers impatient — say a shared rate just once.",
        "Mention increases, decreases, unchanged prices, or weekly trends ONLY when COMPARISON DATA says they are available.",
        "If COMPARISON DATA says unavailable, do NOT mention price movement, trends, yesterday, or weekly comparisons.",
        "When the prices are the same across cities (so the rate part is short), DO add a little more genuinely useful "
        "content to keep the video full and informative. Use ONLY accurate information you can derive from the data given "
        "— for example: the difference between the 24K and 22K rate per gram, a reminder that the final billed price at a "
        "shop will be a bit higher because of making charges and GST, or a simple recap of how today compares with yesterday "
        "/ this week (only if COMPARISON DATA is available). Do NOT invent facts, predictions, or numbers that are not in the data.",
    ]

    return ScriptBrief(
        topic="the daily gold rate",
        data_block=data_block,
        instructions=instructions,
        vocabulary_rules=_gold_vocabulary_rules(meta),
    )


def _gold_short_brief(language: str, state_key: str, price_data: dict) -> ScriptBrief:
    meta = LANGUAGE_META[language]
    config = CHANNEL_CONFIG[state_key]
    date_str = price_data.get("date", "today")

    cities = price_data.get("cities", {})
    g22 = g24 = g22_10 = g24_10 = 0
    if cities:
        first = next(iter(cities.values()), {}) or {}
        g22 = first.get("22k_per_gram", 0)
        g24 = first.get("24k_per_gram", 0)
        g22_10 = first.get("22k_per_10g", 0)
        g24_10 = first.get("24k_per_10g", 0)

    is_cached = price_data.get("cached", False)
    holiday_note = (
        "NOTE: Market is closed today — these are the last closing prices. Mention this in one short phrase."
        if is_cached else
        "These are today's live prices."
    )

    data_block = (
        f"Date: {date_str}\n"
        f"Region: {config['region_name']}\n"
        f"22K gold rate: {g22}/gram (10 grams = {g22_10})\n"
        f"24K gold rate: {g24}/gram (10 grams = {g24_10})\n\n"
        f"DATA NOTE: {holiday_note}\n"
        f'(The "/gram" above is only for brevity — follow the LANGUAGE RULES for how to say it.)'
    )

    instructions = [
        f"Clearly state today's date ({date_str}).",
        "If it's a market holiday, say so in one short phrase.",
        "State today's 22K rate (per gram, and per 10 grams) and 24K rate (per gram, and per 10 grams). "
        "Say each figure once — do NOT repeat or pad.",
        "Do NOT add trend/yesterday/weekly comparisons, making-charges notes, or any extra explanation — keep it short.",
    ]

    return ScriptBrief(
        topic="today's gold rate",
        data_block=data_block,
        instructions=instructions,
        vocabulary_rules=_gold_vocabulary_rules(meta),
    )



def _format_history_context(history_context: dict) -> str:
    if not history_context or not history_context.get("has_comparison"):
        return "Historical comparison is unavailable. Avoid all price movement and trend language."

    previous_date = history_context.get("previous_available_date")
    lines = [f"Previous available market data date: {previous_date}"]
    for city, comparisons in history_context.get("city_comparisons", {}).items():
        parts = []
        for karat in ("22k", "24k"):
            data = comparisons.get(karat)
            if not data:
                continue
            parts.append(
                f"{karat.upper()} {data['direction']} by ₹{abs(data['change_per_gram']):g}/gram "
                f"(from ₹{data['previous_per_gram']:g} to ₹{data['current_per_gram']:g})"
            )
        if parts:
            lines.append(f"- {city}: " + "; ".join(parts))

    weekly_summary = history_context.get("weekly_summary") or {}
    if weekly_summary:
        lines.append("Weekly trend based on stored prior observations:")
        for karat in ("22k", "24k"):
            trend = weekly_summary.get(karat)
            if not trend:
                continue
            lines.append(
                f"- {karat.upper()} average {trend['direction']} by "
                f"₹{abs(trend['change_per_gram']):g}/gram "
                f"from {trend['first_date']} to {trend['last_date']}."
            )

    return "\n".join(lines)


def generate_all_scripts(all_price_data: dict) -> dict:
    """
    Generate scripts for all configured channels.
    Returns: {state_key: {"language": ..., "script": ...}}
    """
    from config import CHANNEL_CONFIG

    results = {}
    for state_key, config in CHANNEL_CONFIG.items():
        language = config["language"]
        state_prices = {
            "date": all_price_data.get("date", ""),
            "cities": all_price_data.get("states", {}).get(state_key, {}).get("cities", {}),
        }

        logger.info(f"Generating {language} script for {state_key}...")
        try:
            script = generate_script(language, state_key, state_prices)
            results[state_key] = {
                "language": language,
                "script": script,
                "channel_id": config["channel_id"],
            }
        except Exception as e:
            logger.error(f"Script generation failed for {state_key}: {e}")
            results[state_key] = {"language": language, "script": None, "error": str(e)}

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Quick test with dummy data
    test_data = {
        "date": "26 June 2026",
        "cities": {
            "Chennai": {
                "22k_per_gram": 6800,
                "24k_per_gram": 7200,
                "22k_per_10g": 68000,
                "24k_per_10g": 72000,
            },
            "Coimbatore": {
                "22k_per_gram": 6790,
                "24k_per_gram": 7190,
                "22k_per_10g": 67900,
                "24k_per_10g": 71900,
            },
        },
    }
    script = generate_script("tamil", "tamil_nadu", test_data)
    print("=== GENERATED SCRIPT ===")
    print(script)
