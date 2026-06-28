"""
script_generator.py — AI script generation for gold price videos
Uses Claude API to generate engaging, natural-sounding scripts in regional languages.
"""

import anthropic
import os
import logging
import time
from config import CHANNEL_CONFIG

logger = logging.getLogger(__name__)

_api_key = os.environ.get("ANTHROPIC_API_KEY")
if not _api_key:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY not found. Add it to your .env file.\n"
        "Get one at: https://console.anthropic.com/api-keys"
    )
client = anthropic.Anthropic(api_key=_api_key)
ANTHROPIC_RETRIES = 3

# Language metadata for prompting
LANGUAGE_META = {
    "tamil": {
        "name": "Tamil",
        "native": "தமிழ்",
        "greeting": "வணக்கம்",
        "unit": "கிராம்",
        "currency": "ரூபாய்",
    },
    "telugu": {
        "name": "Telugu",
        "native": "తెలుగు",
        "greeting": "నమస్కారం",
        "unit": "గ్రాము",
        "currency": "రూపాయలు",
    },
    "kannada": {
        "name": "Kannada",
        "native": "ಕನ್ನಡ",
        "greeting": "ನಮಸ್ಕಾರ",
        "unit": "ಗ್ರಾಂ",
        "currency": "ರೂಪಾಯಿ",
    },
    "malayalam": {
        "name": "Malayalam",
        "native": "മലയാളം",
        "greeting": "നമസ്കാരം",
        "unit": "ഗ്രാം",
        "currency": "രൂപ",
    },
    "hindi": {
        "name": "Hindi",
        "native": "हिन्दी",
        "greeting": "नमस्कार",
        "unit": "ग्राम",
        "currency": "रुपये",
    },
    "marathi": {
        "name": "Marathi",
        "native": "मराठी",
        "greeting": "नमस्कार",
        "unit": "ग्रॅम",
        "currency": "रुपये",
    },
    "bengali": {
        "name": "Bengali",
        "native": "বাংলা",
        "greeting": "নমস্কার",
        "unit": "গ্রাম",
        "currency": "টাকা",
    },
}


def generate_script(language: str, state_key: str, price_data: dict) -> str:
    """
    Generate a 60-90 second video script in the given language.
    price_data: {"date": "...", "cities": {"CityName": {"22k_per_gram": X, ...}}}
    """
    meta = LANGUAGE_META[language]
    config = CHANNEL_CONFIG[state_key]
    date_str = price_data.get("date", "today")

    # Build city price summary for the prompt
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

    prompt = f"""You are a professional news anchor script writer for a YouTube channel about gold prices.

Write a 60-90 second video script in {meta['name']} ({meta['native']}) language for today's gold price update.

TODAY'S DATA:
Date: {date_str}
State/Region: {config['region_name']}
City-wise Gold Rates:
{city_price_text}

DATA NOTE: {data_note}

SCRIPT REQUIREMENTS:
1. Start with "{meta['greeting']}" and a warm welcome to the channel
2. State the date clearly
3. If it's a market holiday, briefly say so and mention these are last closing prices
4. Announce each city's gold rate naturally (22K and 24K, both per gram and per 10 grams)
5. Add 1-2 sentences of context (e.g., "22K is used for jewelry making", "24K is investment grade")
6. End with: ask viewers to LIKE, SUBSCRIBE, and turn on notifications for daily updates
7. Keep it conversational and natural — like a friendly news anchor, NOT robotic
8. Write ONLY in {meta['name']} script (no English mixed in, except numbers and ₹ symbol)
9. Total length: ~150-200 words (for ~60-90 seconds of speech)
10. Do NOT mention price increases, decreases, trends, or comparisons unless comparison data is explicitly provided.

Write ONLY the script text — no stage directions, no [brackets], no notes. Just the spoken words.
"""

    message = _create_message_with_retries(prompt)

    script = message.content[0].text.strip()
    logger.info(f"Generated {language} script ({len(script.split())} words)")
    return script


def _create_message_with_retries(prompt: str):
    last_error = None
    for attempt in range(1, ANTHROPIC_RETRIES + 1):
        try:
            return client.messages.create(
                model="claude-opus-4-8",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            last_error = e
            if attempt == ANTHROPIC_RETRIES:
                break
            wait_seconds = 2 * attempt
            logger.warning(
                f"Anthropic script generation failed on attempt "
                f"{attempt}/{ANTHROPIC_RETRIES}: {e}. Retrying in {wait_seconds}s"
            )
            time.sleep(wait_seconds)
    raise last_error


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
