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
    Generate a 75-110 second video script in the given language.
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
    comparison_note = _format_history_context(price_data.get("history_context", {}))

    prompt = f"""You are a warm, well-spoken host who shares the daily gold rate with viewers — polite and respectful, like a courteous presenter speaking to a wide audience. Friendly and easy to follow, but composed and dignified, NOT slangy or overly casual.

Write a 75-110 second video script in {meta['name']} ({meta['native']}) language for today's gold price update.

TODAY'S DATA:
Date: {date_str}
State/Region: {config['region_name']}
City-wise Gold Rates:
{city_price_text}

(The data above uses the "₹" symbol and the English words "gram"/"10g" only for brevity.
In your spoken script you MUST NOT use them — see the LANGUAGE rules below.)

DATA NOTE: {data_note}

COMPARISON DATA:
{comparison_note}

SCRIPT REQUIREMENTS:
1. Start with "{meta['greeting']}" and a simple, natural welcome to the channel. Keep the welcome plain — do NOT pad it with intensifier words like "very" / "so much" (for example, in Telugu do not use "చాలా" in the welcome). A clean "welcome to our channel" is enough.
2. State the date clearly
3. If it's a market holiday, briefly say so and mention these are last closing prices
4. Announce the gold rates naturally (22K and 24K, both per gram and per 10 grams).
   - IMPORTANT: Do NOT recite the same rates city by city if they are identical. First check the data: if two or more cities share the EXACT same 22K and 24K rates, GROUP them and state the rate ONCE for all of them together (e.g. "in Vijayawada, Visakhapatnam and Guntur the rate is the same today — ..."). Only call out a city separately when its rate actually differs from the others.
   - Repeating the same numbers three times in a row makes viewers impatient — say a shared rate just once.
5. Mention increases, decreases, unchanged prices, or weekly trends ONLY when COMPARISON DATA says they are available
6. If COMPARISON DATA says unavailable, do NOT mention price movement, trends, yesterday, or weekly comparisons
7. When the prices are the same across cities (so the rate part is short), DO add a little more genuinely useful content to keep the video full and informative. Use ONLY accurate information you can derive from the data given — for example: the difference between the 24K and 22K rate per gram, a reminder that the final billed price at a shop will be a bit higher because of making charges and GST, or a simple recap of how today compares with yesterday / this week (only if COMPARISON DATA is available). Do NOT invent facts, predictions, or numbers that are not in the data.
8. ALWAYS end with a clear call to action: ask viewers to LIKE the video, SUBSCRIBE to the channel, and turn on the notification bell for daily updates. This closing MUST be present — never cut it off or skip it.

TONE & STYLE (very important):
- Conversational but a bit formal: warm and easy to follow, yet polite, respectful, and composed — like a courteous presenter, not a casual chat with a buddy.
- Always address the viewer respectfully (use the polite/respectful form of "you" in {meta['name']}).
- Use clear, simple {meta['name']} that anyone can understand. Keep the language clean and proper, but it should sound the way real people speak today.
- IMPORTANT: polite does NOT mean ornate. Use plain, common, everyday words people actually speak — NOT heavy, literary, formal, or bookish vocabulary. If a word sounds like it belongs in a textbook or a formal speech, replace it with the ordinary spoken equivalent.
- Modern spoken {meta['name']} naturally mixes in common, everyday ENGLISH words, and that sounds more natural than a heavy native word. So where the native word is heavy or bookish, PREFER the everyday English word people normally use. For example, instead of heavy native words for "we are sharing", "good news", or "a small note", use the common English equivalents like "share", "good news", "note" — but written in {meta['name']} letters (see LANGUAGE RULES below), the way "like" and "subscribe" are already written in {meta['name']} letters. Use these the way a real {meta['name']} YouTuber would — only common words everyone understands, not full English sentences.
- Use short, natural sentences. Speak directly to the viewer in a gentle, welcoming way (e.g. "let us now look at", "moving on to the next city").
- Don't repeat the exact same sentence structure for every city — vary it naturally while keeping the polished tone.
- Keep it pleasant and easy on the ear — neither stiff and robotic, nor overly informal.

LANGUAGE RULES (critical — the script is read aloud by a text-to-speech voice):
- Write EVERYTHING in the {meta['name']} script (the native alphabet). Do NOT use Latin/English letters at all.
- Common everyday English words ARE allowed (and encouraged where they sound more natural), BUT they MUST be written transliterated in the {meta['name']} script — never in Latin letters. For example write the English word "note" / "good news" / "share" / "update" using {meta['name']} letters (the same way "like" and "subscribe" are written in {meta['name']} letters), so the TTS voice pronounces them correctly.
- For the currency, write the {meta['name']} word "{meta['currency']}" — do NOT use the "₹" symbol or the English word "rupees" (a TTS voice reads "₹" in English).
- For the weight unit, write the {meta['name']} word "{meta['unit']}" for one gram, and the {meta['name']} phrase for "10 {meta['unit']}" for ten grams. Do NOT use the English words "gram", "grams", "g", or "10g".
- Karats: always SPELL OUT the carat word in {meta['name']} (e.g. write the {meta['name']} equivalent of "22 carat" / "24 carat"). You may keep the digits 22 and 24, but NEVER use the Latin letter "K" (as in "22K") — a TTS voice mispronounces it.
- Numeric amounts may be written as digits (e.g. 7250); the TTS voice will read them in {meta['name']}.

LENGTH:
- ~200-280 words (for ~75-110 seconds of speech). It is better to be slightly longer than to drop the closing call to action.

Write ONLY the script text — no stage directions, no [brackets], no notes. Just the spoken words.
"""

    message = _create_message_with_retries(prompt)

    if getattr(message, "stop_reason", None) == "max_tokens":
        logger.warning(
            f"{language} script hit the max_tokens limit and was likely truncated "
            f"(closing call to action may be missing). Consider raising max_tokens."
        )

    script = message.content[0].text.strip()
    logger.info(f"Generated {language} script ({len(script.split())} words)")
    return script


def generate_short_script(language: str, state_key: str, price_data: dict) -> str:
    """
    Generate a very short (~30 second) script for a vertical Shorts/Reels video.
    Punchy headline style: greeting + today's 22K/24K rate (said once) + a quick
    subscribe call to action. No trend, no extra context — built to stay under ~35s.
    """
    meta = LANGUAGE_META[language]
    config = CHANNEL_CONFIG[state_key]
    date_str = price_data.get("date", "today")

    # Average the per-gram rates across the scraped cities so the short states one figure.
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

    prompt = f"""You are a warm, well-spoken host making a SHORT (under 35 seconds) vertical video about today's gold rate.

Write a very short script in {meta['name']} ({meta['native']}) language. This is for a YouTube Short / Instagram Reel, so it must be punchy and quick.

TODAY'S DATA:
Date: {date_str}
Region: {config['region_name']}
22K gold rate: {g22}/gram (10 grams = {g22_10})
24K gold rate: {g24}/gram (10 grams = {g24_10})

DATA NOTE: {holiday_note}
(The "/gram" above is only for brevity — follow the LANGUAGE RULES for how to say it.)

WHAT TO SAY (keep it tight, in this order):
1. A quick "{meta['greeting']}" + one short line welcoming viewers to today's gold rate, and clearly state today's date ({date_str}).
2. If it's a market holiday, say so in one short phrase.
3. State today's 22K rate (per gram, and per 10 grams) and 24K rate (per gram, and per 10 grams). Say each figure once — do NOT repeat or pad.
4. End with ONE short, friendly line asking viewers to SUBSCRIBE and turn on the bell for daily updates. This closing MUST be present.
Do NOT add trend/yesterday/weekly comparisons, making-charges notes, or any extra explanation — keep it short.

TONE & STYLE:
- Conversational but a bit formal — warm, polite, and natural, like a courteous presenter.
- Use plain, everyday words people actually speak — NOT heavy, literary, or bookish vocabulary.
- Modern spoken {meta['name']} naturally mixes in common English words; where the native word is heavy, prefer the everyday English word (e.g. "subscribe", "update", "rate") written in {meta['name']} letters.

LANGUAGE RULES (critical — the script is read aloud by a text-to-speech voice):
- Write EVERYTHING in the {meta['name']} script (the native alphabet). Do NOT use Latin/English letters at all. English words are fine but must be transliterated into {meta['name']} letters.
- For the currency, write the {meta['name']} word "{meta['currency']}" — do NOT use the "₹" symbol or the English word "rupees".
- For the weight unit, write the {meta['name']} word "{meta['unit']}" for one gram and the {meta['name']} phrase for "10 {meta['unit']}" for ten grams. Do NOT use the English words "gram"/"grams"/"g".
- Carats: SPELL OUT the carat word in {meta['name']} (keep the digits 22 and 24, but never the Latin letter "K").
- Numbers may be written as digits.

LENGTH: about 55-75 words total (roughly 25-35 seconds of speech). Keep it short.

Write ONLY the script text — no stage directions, no [brackets], no notes. Just the spoken words.
"""

    message = _create_message_with_retries(prompt, max_tokens=1000)

    if getattr(message, "stop_reason", None) == "max_tokens":
        logger.warning(f"{language} short script hit the max_tokens limit and may be truncated.")

    script = message.content[0].text.strip()
    logger.info(f"Generated {language} short script ({len(script.split())} words)")
    return script


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


def _create_message_with_retries(prompt: str, max_tokens: int = 2000):
    last_error = None
    for attempt in range(1, ANTHROPIC_RETRIES + 1):
        try:
            return client.messages.create(
                model="claude-opus-4-8",
                # Indic scripts tokenize into many tokens per word, so a ~200-280
                # word regional script needs significant headroom. Too low a limit
                # truncates the script mid-sentence and drops the closing call to action.
                max_tokens=max_tokens,
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
