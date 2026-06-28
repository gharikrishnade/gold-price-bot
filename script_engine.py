"""
script_engine.py — Shared, domain-agnostic script generation for the video platform.

Owns everything that is the same for every show (gold, stocks, horoscope, …):
the host persona, tone/style rules, the regional-language + TTS rules, the
mandatory call-to-action, length targets, and the Anthropic call (retries +
truncation guard).

A content module supplies only a ``ScriptBrief`` (the domain facts + a few
domain-specific instructions and vocabulary rules); the engine applies the shared
voice. This is how new shows inherit correct regional scripting for free.

Tracker: PLAT-004 (shared script engine).
"""
from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field

import anthropic

logger = logging.getLogger(__name__)

_api_key = os.environ.get("ANTHROPIC_API_KEY")
if not _api_key:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY not found. Add it to your .env file.\n"
        "Get one at: https://console.anthropic.com/api-keys"
    )
client = anthropic.Anthropic(api_key=_api_key)
ANTHROPIC_RETRIES = 3
MODEL = "claude-opus-4-8"

# Per-language metadata shared across all shows.
LANGUAGE_META = {
    "tamil":     {"name": "Tamil",     "native": "தமிழ்",   "greeting": "வணக்கம்",   "unit": "கிராம்",  "currency": "ரூபாய்"},
    "telugu":    {"name": "Telugu",    "native": "తెలుగు",  "greeting": "నమస్కారం", "unit": "గ్రాము",  "currency": "రూపాయలు"},
    "kannada":   {"name": "Kannada",   "native": "ಕನ್ನಡ",   "greeting": "ನಮಸ್ಕಾರ",  "unit": "ಗ್ರಾಂ",   "currency": "ರೂಪಾಯಿ"},
    "malayalam": {"name": "Malayalam", "native": "മലയാളം",  "greeting": "നമസ്കാരം", "unit": "ഗ്രാം",   "currency": "രൂപ"},
    "hindi":     {"name": "Hindi",     "native": "हिन्दी",   "greeting": "नमस्कार",   "unit": "ग्राम",   "currency": "रुपये"},
    "marathi":   {"name": "Marathi",   "native": "मराठी",   "greeting": "नमस्कार",   "unit": "ग्रॅम",   "currency": "रुपये"},
    "bengali":   {"name": "Bengali",   "native": "বাংলা",   "greeting": "নমস্কার",   "unit": "গ্রাম",   "currency": "টাকা"},
}


@dataclass
class ScriptBrief:
    """The domain-specific content a module hands to the shared script engine.

    The engine wraps this in the shared persona / tone / language / CTA rules.
    """
    topic: str                                        # e.g. "the daily gold rate in Andhra Pradesh"
    data_block: str                                   # structured facts the script must use
    instructions: list[str] = field(default_factory=list)      # domain 'what to say' steps (greeting + CTA are added by the engine)
    vocabulary_rules: list[str] = field(default_factory=list)   # domain language rules (currency/unit/etc.), already in target language
    disclaimers: list[str] = field(default_factory=list)        # e.g. "not financial advice" — included naturally


_VARIANTS = {
    "long": {
        "duration": "75-110 second",
        "length": (
            "~200-280 words (for ~75-110 seconds of speech). It is better to be "
            "slightly longer than to drop the closing call to action."
        ),
        "max_tokens": 2000,
        "cta": (
            "ALWAYS end with a clear call to action: ask viewers to LIKE the video, "
            "SUBSCRIBE to the channel, and turn on the notification bell for daily updates. "
            "This closing MUST be present — never cut it off or skip it."
        ),
    },
    "short": {
        "duration": "very short (under 35 seconds, for a YouTube Short / Instagram Reel — punchy and quick)",
        "length": "about 55-75 words total (roughly 25-35 seconds of speech). Keep it short.",
        "max_tokens": 1000,
        "cta": (
            "End with ONE short, friendly line asking viewers to SUBSCRIBE and turn on "
            "the bell for daily updates. This closing MUST be present."
        ),
    },
}


def _tone_block(name: str) -> str:
    return f"""TONE & STYLE (very important):
- Conversational but a bit formal: warm and easy to follow, yet polite, respectful, and composed — like a courteous presenter, not a casual chat with a buddy.
- Always address the viewer respectfully (use the polite/respectful form of "you" in {name}).
- Use clear, simple {name} that anyone can understand. Keep the language clean and proper, but it should sound the way real people speak today.
- IMPORTANT: polite does NOT mean ornate. Use plain, common, everyday words people actually speak — NOT heavy, literary, formal, or bookish vocabulary. If a word sounds like it belongs in a textbook or a formal speech, replace it with the ordinary spoken equivalent.
- Modern spoken {name} naturally mixes in common, everyday ENGLISH words, and that sounds more natural than a heavy native word. So where the native word is heavy or bookish, PREFER the everyday English word people normally use (e.g. "share", "good news", "note", "update") — but written in {name} letters (see LANGUAGE RULES), the way "like" and "subscribe" are written in {name} letters. Use these the way a real {name} YouTuber would — only common words everyone understands, not full English sentences.
- Use short, natural sentences. Speak directly to the viewer in a gentle, welcoming way.
- Don't repeat the exact same sentence structure throughout — vary it naturally while keeping the polished tone.
- Keep it pleasant and easy on the ear — neither stiff and robotic, nor overly informal."""


def _language_block(name: str, vocabulary_rules: list[str]) -> str:
    vocab = ("\n" + "\n".join(vocabulary_rules)) if vocabulary_rules else ""
    return f"""LANGUAGE RULES (critical — the script is read aloud by a text-to-speech voice):
- Write EVERYTHING in the {name} script (the native alphabet). Do NOT use Latin/English letters at all.
- Common everyday English words ARE allowed (and encouraged where they sound more natural), BUT they MUST be written transliterated in the {name} script — never in Latin letters. For example write the English word "note" / "good news" / "share" / "update" using {name} letters (the same way "like" and "subscribe" are written in {name} letters), so the TTS voice pronounces them correctly.{vocab}
- Numeric amounts may be written as digits (e.g. 7250); the TTS voice will read them in {name}."""


def _build_prompt(meta: dict, brief: ScriptBrief, variant: str) -> str:
    name, native, greeting = meta["name"], meta["native"], meta["greeting"]
    spec = _VARIANTS[variant]

    steps = [
        f'Start with "{greeting}" and a simple, natural welcome to the channel. Keep the welcome '
        f'plain — do NOT pad it with intensifier words like "very" / "so much". A clean '
        f'"welcome to our channel" is enough.',
        *brief.instructions,
        spec["cta"],
    ]
    numbered = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))

    disclaimer_block = ""
    if brief.disclaimers:
        lines = "\n".join(f"- {d}" for d in brief.disclaimers)
        disclaimer_block = f"\nDISCLAIMERS (state clearly and naturally in the script):\n{lines}\n"

    return f"""You are a warm, well-spoken host who shares {brief.topic} with viewers — polite and respectful, like a courteous presenter speaking to a wide audience. Friendly and easy to follow, but composed and dignified, NOT slangy or overly casual.

Write a {spec['duration']} script in {name} ({native}) language.

DATA / FACTS:
{brief.data_block}
{disclaimer_block}
WHAT TO SAY:
{numbered}

{_tone_block(name)}

{_language_block(name, brief.vocabulary_rules)}

LENGTH:
- {spec['length']}

Write ONLY the script text — no stage directions, no [brackets], no notes. Just the spoken words.
"""


def generate(language: str, brief: ScriptBrief, *, variant: str = "long") -> str:
    """Generate a script in ``language`` from a domain ``ScriptBrief``.

    variant: "long" (~75-110s) or "short" (~30s Shorts/Reels).
    """
    if language not in LANGUAGE_META:
        raise KeyError(f"Unknown language '{language}'. Known: {', '.join(LANGUAGE_META)}")
    if variant not in _VARIANTS:
        raise ValueError(f"Unknown script variant '{variant}'. Use one of: {', '.join(_VARIANTS)}")

    meta = LANGUAGE_META[language]
    prompt = _build_prompt(meta, brief, variant)
    message = _create_message_with_retries(prompt, max_tokens=_VARIANTS[variant]["max_tokens"])

    if getattr(message, "stop_reason", None) == "max_tokens":
        logger.warning(
            f"{language} {variant} script hit the max_tokens limit and was likely truncated "
            f"(closing call to action may be missing). Consider raising max_tokens."
        )

    script = message.content[0].text.strip()
    logger.info(f"Generated {language} {variant} script ({len(script.split())} words)")
    return script


def _create_message_with_retries(prompt: str, max_tokens: int = 2000):
    last_error = None
    for attempt in range(1, ANTHROPIC_RETRIES + 1):
        try:
            return client.messages.create(
                model=MODEL,
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
