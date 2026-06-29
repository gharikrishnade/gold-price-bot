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
import base64
import mimetypes
from datetime import date
from html import escape
from pathlib import Path

from jobs_config import jobs_for_module
from script_engine import LANGUAGE_META, ScriptBrief, generate as _engine_generate
from template_kit import Brand, render_html_to_image, css_font_stack
from youtube_uploader import _yt_language_code
from thumbnail_generator import FONT_CANDIDATES, ensure_language_font

from modules.base import ContentModule, ValidationResult

logger = logging.getLogger("modules.horoscope")
ROOT_DIR = Path(__file__).resolve().parent.parent

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
    sign = _base_sign(channel)
    return ZODIAC.get(sign, (sign.title(), "✷", ""))


def _base_sign(channel: str) -> str:
    """Allow future localized channels such as aries_telugu without duplicating sign logic."""
    if channel in ZODIAC:
        return channel
    for suffix in ("_telugu", "_hindi", "_tamil", "_kannada", "_malayalam", "_marathi", "_bengali"):
        if channel.endswith(suffix):
            return channel.removesuffix(suffix)
    return channel

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
    "telugu": {
        "title": "ఈరోజు రాశి ఫలాలు", "rashi": "రాశి",
        "lucky_number": "అదృష్ట సంఖ్య", "mood": "ఈరోజు భావం", "lucky_color": "అదృష్ట రంగు",
        "lucky_direction": "శుభ దిక్కు", "nakshatra": "నక్షత్రం / పాదం",
        "career": "ఉద్యోగం", "finance": "ఆర్థికం", "love": "ప్రేమ / కుటుంబం", "health": "ఆరోగ్యం",
        "remedy": "పరిహారం", "mantra": "మంత్రం", "deity": "ఆరాధ్య దైవం",
        "disclaimer": "ఇది వినోదం కోసం మాత్రమే", "blessing": "శుభం భవతు",
        "signs": {"aries": "మేషం", "taurus": "వృషభం", "gemini": "మిథునం", "cancer": "కర్కాటకం",
                   "leo": "సింహం", "virgo": "కన్య", "libra": "తుల", "scorpio": "వృశ్చికం",
                   "sagittarius": "ధనుస్సు", "capricorn": "మకరం", "aquarius": "కుంభం", "pisces": "మీనం"},
        "colors": {"Red": "ఎరుపు", "Blue": "నీలం", "Green": "ఆకుపచ్చ", "Gold": "బంగారు", "Purple": "ఊదా",
                    "Silver": "వెండి", "Orange": "నారింజ", "Teal": "నీలి ఆకుపచ్చ", "Pink": "గులాబీ", "White": "తెలుపు"},
        "moods": {"Bright": "ఉత్సాహం", "Calm": "శాంతి", "Energetic": "శక్తి", "Focused": "ఏకాగ్రత",
                   "Hopeful": "ఆశ", "Cheerful": "ఆనందం", "Confident": "ఆత్మవిశ్వాసం", "Balanced": "సమతుల్యం"},
        "weekdays": ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"],
        "months": ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"],
    },
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

_SIGN_DETAILS = {
    "aries":       {"nakshatra": "అశ్విని, భరణి, కృత్తిక 1వ పాదం", "deity": "శ్రీ సుబ్రహ్మణ్య స్వామి", "mantra": "ఓం స్కందాయ నమః", "direction": "తూర్పు"},
    "taurus":      {"nakshatra": "రోహిణి 3వ పాదం", "deity": "శ్రీ మహాలక్ష్మి", "mantra": "ఓం శ్రీం మహాలక్ష్మ్యై నమః", "direction": "ఆగ్నేయం"},
    "gemini":      {"nakshatra": "మృగశిర 4వ పాదం", "deity": "శ్రీ విష్ణుమూర్తి", "mantra": "ఓం నమో నారాయణాయ", "direction": "ఉత్తరం"},
    "cancer":      {"nakshatra": "పుష్యమి 1వ పాదం", "deity": "శ్రీ పార్వతీ దేవి", "mantra": "ఓం పార్వత్యై నమః", "direction": "వాయువ్యం"},
    "leo":         {"nakshatra": "మఖ 2వ పాదం", "deity": "శ్రీ సూర్యనారాయణ", "mantra": "ఓం సూర్యాయ నమః", "direction": "తూర్పు"},
    "virgo":       {"nakshatra": "హస్త 3వ పాదం", "deity": "శ్రీ గణపతి", "mantra": "ఓం గం గణపతయే నమః", "direction": "ఉత్తరం"},
    "libra":       {"nakshatra": "స్వాతి 1వ పాదం", "deity": "శ్రీ లక్ష్మీ నారాయణ", "mantra": "ఓం లక్ష్మీ నారాయణాయ నమః", "direction": "పడమర"},
    "scorpio":     {"nakshatra": "అనూరాధ 2వ పాదం", "deity": "శ్రీ ఆంజనేయ స్వామి", "mantra": "ఓం హనుమతే నమః", "direction": "దక్షిణం"},
    "sagittarius": {"nakshatra": "మూల 3వ పాదం", "deity": "శ్రీ దత్తాత్రేయ స్వామి", "mantra": "ఓం దత్తాత్రేయాయ నమః", "direction": "ఈశాన్యం"},
    "capricorn":   {"nakshatra": "శ్రవణం 2వ పాదం", "deity": "శ్రీ శనేశ్వర స్వామి", "mantra": "ఓం శనైశ్చరాయ నమః", "direction": "పడమర"},
    "aquarius":    {"nakshatra": "శతభిషం 1వ పాదం", "deity": "శ్రీ శివుడు", "mantra": "ఓం నమః శివాయ", "direction": "వాయువ్యం"},
    "pisces":      {"nakshatra": "రేవతి 4వ పాదం", "deity": "శ్రీ సాయి బాబా", "mantra": "ఓం సాయినాథాయ నమః", "direction": "ఈశాన్యం"},
}

_PREDICTION_BANK = {
    "career": [
        "ఉద్యోగంలో కొత్త అవకాశాలు వస్తాయి. మీ కృషికి గుర్తింపు లభిస్తుంది. సహోద్యోగులతో మంచి సంబంధాలు కొనసాగిస్తారు.",
        "పనుల్లో ప్రాధాన్యత క్రమం పాటిస్తే మంచి పురోగతి కనిపిస్తుంది.",
        "మీ ఆలోచనను స్పష్టంగా చెప్పడం వల్ల సహకారం సులభంగా దొరుకుతుంది.",
        "కొత్త పని మొదలుపెట్టే ముందు చిన్న ప్రణాళిక వేసుకుంటే ఒత్తిడి తగ్గుతుంది.",
    ],
    "finance": [
        "ఆదాయం పెరిగే సూచనలు ఉన్నాయి. అనవసర ఖర్చులను తగ్గించండి. పెట్టుబడులకు అనుకూలమైన సమయం.",
        "ఖర్చుల విషయంలో తొందరపడకుండా అవసరమైన వాటికే ప్రాధాన్యం ఇవ్వండి.",
        "చిన్న పొదుపు నిర్ణయం తర్వాతి రోజుల్లో ఉపయోగపడే అవకాశం ఉంది.",
        "పెద్ద కొనుగోలు ముందు మరోసారి వివరాలు చూసుకోవడం మంచిది.",
    ],
    "love": [
        "ప్రేమ జీవితంలో ఆనందం పెరుగుతుంది. జీవిత భాగస్వామితో అన్యోన్యంగా ఉంటారు. సింగిల్స్ కు మంచి పరిచయాలు ఏర్పడవచ్చు.",
        "కుటుంబం లేదా ప్రియమైన వారితో మృదువుగా మాట్లాడితే అపార్థాలు తగ్గుతాయి.",
        "మనసులో ఉన్న మాటను ప్రశాంతంగా చెప్పడం సంబంధాలకు మేలు చేస్తుంది.",
        "అవతలి వారి భావనను వినడం ఈరోజు ముఖ్యమైన బలం అవుతుంది.",
    ],
    "health": [
        "ఆరోగ్యంగా ఉంటారు. యోగా, ధ్యానం చేయడం వల్ల మానసిక ప్రశాంతత లభిస్తుంది. ఆహారంలో జాగ్రత్త వహించండి.",
        "నీరు, తేలికపాటి ఆహారం, చిన్న నడక మీ శక్తిని నిలబెడతాయి.",
        "విశ్రాంతికి సమయం కేటాయిస్తే మానసిక ప్రశాంతత పెరుగుతుంది.",
        "రోజువారీ అలవాట్లలో చిన్న క్రమశిక్షణ ఆరోగ్యానికి తోడ్పడుతుంది.",
    ],
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


def _daily_predictions(sign: str, iso_date: str) -> dict:
    """Stable, general guidance blocks for the poster and the spoken script."""
    if sign == "aries":
        return {key: values[0] for key, values in _PREDICTION_BANK.items()}
    h = int(hashlib.sha256(f"predictions:{sign}:{iso_date}".encode()).hexdigest(), 16)
    return {
        key: values[(h >> (i * 6)) % len(values)]
        for i, (key, values) in enumerate(_PREDICTION_BANK.items())
    }


def _localized_date(d: date, language: str) -> tuple[str, str]:
    if language == "telugu":
        L = _locale(language)
        return f"{d.day} {L['months'][d.month - 1]} {d.year}", L["weekdays"][d.weekday()]
    return d.strftime("%d %b %Y"), d.strftime("%A")


def _image_data_uri(*paths: str) -> str | None:
    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            path = ROOT_DIR / path
        if not path.exists():
            continue
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    return None


def _devotional_card_html(data: dict, language: str, fmt: str, width: int, height: int) -> str:
    """Devotional, symbol-rich, regional-language horoscope card (landscape/portrait)."""
    if language == "telugu":
        return _telugu_poster_html(data, fmt, width, height)

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


def _telugu_poster_html(data: dict, fmt: str, width: int, height: int) -> str:
    """Rich Telugu devotional poster with structured guidance sections."""
    L = _locale("telugu")
    sign = data["sign"]
    glyph = data.get("glyph", "✷")
    sign_name = L["signs"].get(sign, data.get("sign_display", sign.title()))
    details = data.get("sign_details", _SIGN_DETAILS.get(sign, {}))
    predictions = data.get("predictions", {})
    b = HOROSCOPE_BRAND

    base = 1080 if fmt == "portrait" else 1280
    sc = width / base
    def px(v): return round(v * sc)
    portrait = fmt == "portrait"

    if portrait:
        return _telugu_reference_portrait_html(data, width, height)

    reg = css_font_stack(",".join(FONT_CANDIDATES.get("telugu", ["Noto Sans Telugu"])))
    glyph_font = "'Apple Symbols','Arial Unicode MS','Segoe UI Symbol',sans-serif"
    sage_src = _image_data_uri("assets/avatars/horoscope_sage.png", "assets/avatars/horoscope_sage.jpg")
    sage_html = (
        f'<div class="sage"><img src="{sage_src}" alt=""></div>'
        if sage_src else '<div class="sage sage-empty"><div>ॐ</div></div>'
    )

    section_icons = {"career": "✦", "finance": "₹", "love": "♡", "health": "+"}
    section_html = "".join(
        f"""<div class="section">
      <div class="section-icon">{escape(section_icons[key])}</div>
      <div><div class="section-title">{escape(L[key])}</div>
      <div class="section-text">{escape(predictions.get(key, ""))}</div></div>
    </div>"""
        for key in ("career", "finance", "love", "health")
    )
    luck_items = [
        (L["lucky_color"], L["colors"].get(data["lucky_color"], data["lucky_color"])),
        (L["lucky_number"], str(data["lucky_number"])),
        (L["lucky_direction"], details.get("direction", "తూర్పు")),
    ]
    luck_html = "".join(
        f'<div class="luck-item"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
        for label, value in luck_items
    )

    title_size = px(58 if portrait else 38)
    sign_size = px(66 if portrait else 38)
    body_size = px(28 if portrait else 19)
    small_size = px(22 if portrait else 16)
    frame = px(24)
    content_gap = px(22 if portrait else 12)
    hero_min = px(500 if portrait else 218)
    glyph_ring = px(200 if portrait else 118)
    glyph_size = px(104 if portrait else 62)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body{{width:{width}px;height:{height}px;overflow:hidden;}}
  body{{font-family:{reg}; color:{b.text}; background:
    radial-gradient(circle at 50% 0%, rgba(255,195,92,.28), transparent 34%),
    linear-gradient(180deg, #46110d 0%, #230605 54%, #120303 100%);
    padding:{frame}px; text-rendering:geometricPrecision; font-feature-settings:"kern";}}
  .poster{{position:relative; width:100%; height:100%; border:{px(4)}px solid {b.accent};
    border-radius:{px(34)}px; overflow:hidden; background:
    linear-gradient(135deg, rgba(255,221,143,.13), transparent 28%),
    radial-gradient(circle at 50% 45%, rgba(127,45,14,.92), rgba(36,8,7,.96) 68%);
    box-shadow:inset 0 0 0 {px(2)}px rgba(255,239,184,.28), inset 0 0 {px(80)}px rgba(0,0,0,.55);}}
  .ornament{{position:absolute; inset:{px(18)}px; border:{px(2)}px solid rgba(244,197,66,.42);
    border-radius:{px(24)}px; pointer-events:none;}}
  .corner{{position:absolute; color:{b.accent}; font-size:{px(30)}px; opacity:.75;}}
  .content{{position:relative; height:100%; display:flex; flex-direction:column; gap:{content_gap}px;
    padding:{px(32 if portrait else 22)}px {px(42 if portrait else 34)}px;}}
  .topbar{{display:flex; align-items:center; justify-content:center; gap:{px(18)}px; color:{b.accent};}}
  .diya{{font-size:{px(34 if portrait else 24)}px; line-height:1;}}
  .title{{font-size:{title_size}px; line-height:1.25; font-weight:900; color:{b.accent};
    padding:{px(12)}px {px(34)}px; border:{px(2)}px solid rgba(244,197,66,.62);
    border-radius:{px(999)}px; background:linear-gradient(180deg, rgba(80,18,12,.92), rgba(24,4,4,.88));
    box-shadow:0 {px(10)}px {px(26)}px rgba(0,0,0,.28);}}
  .datebar{{align-self:center; display:flex; gap:{px(18)}px; align-items:center; color:#ffe9b2;
    font-size:{small_size}px; line-height:1.4; padding:{px(8)}px {px(24)}px;
    border-radius:{px(999)}px; background:rgba(0,0,0,.28); border:{px(1)}px solid rgba(244,197,66,.38);}}
  .hero{{display:grid; grid-template-columns:{'1fr' if portrait else '235px 1fr 230px'}; gap:{px(18)}px;
    align-items:center; min-height:{hero_min}px;}}
  .sage{{display:{'none' if portrait else 'flex'}; align-items:flex-end; justify-content:center; height:{px(172)}px;
    border-radius:{px(18)}px; overflow:hidden; border:{px(2)}px solid rgba(244,197,66,.48);
    background:rgba(0,0,0,.25);}}
  .sage img{{width:100%; height:100%; object-fit:cover; object-position:center 18%;}}
  .sage-empty{{align-items:center; color:{b.accent}; font-size:{px(60)}px;}}
  .signbox{{text-align:center; min-width:0;}}
  .glyph-ring{{width:{glyph_ring}px; height:{glyph_ring}px; margin:0 auto {px(12)}px;
    display:flex; align-items:center; justify-content:center; border-radius:50%;
    border:{px(5)}px solid {b.accent}; background:radial-gradient(circle at 50% 38%, #ffd17a 0%, #dd7c22 58%, #67220a 100%);
    box-shadow:0 0 {px(34)}px rgba(244,197,66,.36), inset 0 0 {px(30)}px rgba(0,0,0,.36);}}
  .glyph{{font-family:{glyph_font}; font-size:{glyph_size}px; color:#351205; line-height:1;}}
  .sign{{font-size:{sign_size}px; line-height:1.22; font-weight:900; color:#fff6df;}}
  .nak{{margin-top:{px(7)}px; font-size:{small_size}px; line-height:1.45; color:#ffd884;}}
  .luck{{display:grid; grid-template-columns:{'repeat(3, 1fr)' if portrait else '1fr'}; gap:{px(10)}px; align-self:center; width:100%;}}
  .luck-item{{padding:{px(9 if portrait else 10)}px {px(10)}px; border-radius:{px(14)}px; background:rgba(0,0,0,.28);
    border:{px(1)}px solid rgba(244,197,66,.48); text-align:center;}}
  .luck-item span{{display:block; font-size:{px(18 if portrait else 16)}px; line-height:1.35; color:#ffb96f; font-weight:800;}}
  .luck-item strong{{display:block; margin-top:{px(4)}px; font-size:{px(22 if portrait else 19)}px; line-height:1.35; color:#fff3df;}}
  .sections{{display:grid; grid-template-columns:{'1fr' if portrait else '1fr 1fr'}; gap:{px(14)}px;}}
  .section{{display:grid; grid-template-columns:{px(54 if portrait else 42)}px 1fr; gap:{px(13)}px;
    align-items:start; min-height:{px(150 if portrait else 96)}px; padding:{px(16 if portrait else 12)}px;
    border-radius:{px(18)}px; border:{px(1)}px solid rgba(244,197,66,.42);
    background:linear-gradient(180deg, rgba(255,206,107,.12), rgba(0,0,0,.24));}}
  .section-icon{{height:{px(54 if portrait else 42)}px; width:{px(54 if portrait else 42)}px; border-radius:50%;
    display:flex; align-items:center; justify-content:center; color:#411104; background:{b.accent};
    font-size:{px(28 if portrait else 22)}px; line-height:1; font-weight:900;}}
  .section-title{{font-size:{px(28 if portrait else 20)}px; line-height:1.35; color:{b.accent}; font-weight:900;}}
  .section-text{{margin-top:{px(5)}px; font-size:{body_size}px; line-height:1.55; color:#fff2dc;}}
  .remedy{{display:grid; grid-template-columns:{'1fr' if portrait else '1fr 1fr'}; gap:{px(12)}px;
    padding:{px(18 if portrait else 13)}px; border:{px(2)}px solid rgba(244,197,66,.5);
    border-radius:{px(18)}px; background:rgba(0,0,0,.31);}}
  .remedy-block span{{display:block; font-size:{small_size}px; line-height:1.35; color:#ffb96f; font-weight:800;}}
  .remedy-block strong{{display:block; margin-top:{px(5)}px; font-size:{px(31 if portrait else 21)}px; line-height:1.45; color:#fff7e7;}}
  .footer{{margin-top:auto; text-align:center; color:{b.accent};}}
  .blessing{{font-size:{px(42 if portrait else 26)}px; line-height:1.35; font-weight:900;}}
  .disclaimer{{font-size:{px(22 if portrait else 16)}px; line-height:1.35; color:{b.text_muted}; margin-top:{px(3)}px;}}
</style></head><body><div class="poster">
  <div class="ornament"></div>
  <div class="corner" style="top:{px(28)}px;left:{px(34)}px;">✦</div>
  <div class="corner" style="top:{px(28)}px;right:{px(34)}px;">✦</div>
  <div class="corner" style="bottom:{px(28)}px;left:{px(34)}px;">✦</div>
  <div class="corner" style="bottom:{px(28)}px;right:{px(34)}px;">✦</div>
  <div class="content">
    <div class="topbar"><div class="diya">॥</div><div class="title">{escape(L["title"])}</div><div class="diya">॥</div></div>
    <div class="datebar"><strong>{escape(data.get("weekday", ""))}</strong><span>{escape(data.get("localized_date", data["date"]))}</span></div>
    <div class="hero">
      {sage_html}
      <div class="signbox">
        <div class="glyph-ring"><div class="glyph">{glyph}</div></div>
        <div class="sign">{escape(sign_name)} <span>{escape(L["rashi"])}</span></div>
        <div class="nak">{escape(L["nakshatra"])}: {escape(details.get("nakshatra", ""))}</div>
      </div>
      <div class="luck">{luck_html}</div>
    </div>
    <div class="sections">{section_html}</div>
    <div class="remedy">
      <div class="remedy-block"><span>{escape(L["deity"])}</span><strong>{escape(details.get("deity", ""))}</strong></div>
      <div class="remedy-block"><span>{escape(L["mantra"])}</span><strong>{escape(details.get("mantra", ""))}</strong></div>
    </div>
    <div class="footer"><div class="blessing">{escape(L["blessing"])}</div><div class="disclaimer">{escape(L["disclaimer"])}</div></div>
  </div>
</div></body></html>"""


def _telugu_reference_portrait_html(data: dict, width: int, height: int) -> str:
    """Portrait poster recreated from the supplied Telugu horoscope reference."""
    L = _locale("telugu")
    sign = data["sign"]
    sign_name = L["signs"].get(sign, data.get("sign_display", sign.title()))
    details = data.get("sign_details", _SIGN_DETAILS.get(sign, {}))
    predictions = data.get("predictions", {})
    color = L["colors"].get(data["lucky_color"], data["lucky_color"])
    number = str(data["lucky_number"])
    direction = details.get("direction", "తూర్పు")
    reg = css_font_stack(",".join(FONT_CANDIDATES.get("telugu", ["Noto Sans Telugu"])))
    sage_src = _image_data_uri("assets/horoscope/telugu_sage_reference.png", "assets/avatars/horoscope_sage.png")
    ram_src = _image_data_uri("assets/horoscope/aries_ram_reference.png")

    sc = width / 1080
    def px(v): return round(v * sc)

    sage_html = f'<img src="{sage_src}" alt="">' if sage_src else ""
    ram_html = f'<img src="{ram_src}" alt="">' if ram_src else f'<div class="ram-glyph">{escape(data.get("glyph", "♈"))}</div>'
    date_text = escape(data.get("localized_date", data["date"]))
    weekday = escape(data.get("weekday", ""))
    nak = escape(details.get("nakshatra", ""))
    english = escape(data.get("sign_display", sign.title()).upper())

    rows = [
        ("briefcase", L["career"], predictions.get("career", "")),
        ("coins", L["finance"], predictions.get("finance", "")),
        ("heart", "ప్రేమ", predictions.get("love", "")),
        ("cross", L["health"], predictions.get("health", "")),
    ]
    rows_html = "".join(
        f"""<div class="pred-row">
      <div class="pred-label"><div class="icon {icon}"></div><strong>{escape(label)}</strong></div>
      <div class="pred-text">{escape(text)}</div>
    </div>"""
        for icon, label, text in rows
    )

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  html,body{{width:{width}px;height:{height}px;overflow:hidden;}}
  body{{font-family:{reg}; background:#120504; color:#2b1208; text-rendering:geometricPrecision;
    font-feature-settings:"kern";}}
  .poster{{position:relative; width:{width}px; height:{height}px; overflow:hidden;
    background:
      radial-gradient(circle at 70% 34%, rgba(135,18,12,.62), transparent 31%),
      radial-gradient(circle at 30% 35%, rgba(255,174,49,.18), transparent 35%),
      linear-gradient(180deg, #130604 0%, #351006 51%, #fff0c9 52%, #fff3cf 94%, #160604 94%);
    border:{px(3)}px solid #e8a91d;}}
  .poster::before{{content:""; position:absolute; inset:{px(16)}px; border:{px(2)}px solid #d99a16;
    border-radius:{px(14)}px; pointer-events:none; box-shadow:inset 0 0 {px(56)}px rgba(0,0,0,.36);}}
  .corner{{position:absolute; color:#f2b51d; font-size:{px(46)}px; line-height:1; font-family:serif; z-index:5;}}
  .c1{{left:{px(20)}px;top:{px(16)}px;}} .c2{{right:{px(20)}px;top:{px(16)}px; transform:scaleX(-1);}}
  .c3{{left:{px(20)}px;bottom:{px(18)}px; transform:scaleY(-1);}} .c4{{right:{px(20)}px;bottom:{px(18)}px; transform:scale(-1);}}
  .title{{position:absolute; top:{px(36)}px; left:{px(78)}px; right:{px(78)}px; z-index:4;
    color:#ffd758; font-size:{px(76)}px; line-height:1.12; font-weight:900; text-align:center;
    text-shadow:0 {px(4)}px 0 #6b3108, 0 {px(8)}px {px(18)}px rgba(0,0,0,.72);}}
  .orn-line{{position:absolute; top:{px(150)}px; left:{px(160)}px; right:{px(160)}px; height:{px(2)}px;
    background:linear-gradient(90deg, transparent, #d99a16 18%, #f8ce4b 50%, #d99a16 82%, transparent); z-index:4;}}
  .orn-line::after{{content:"✥"; position:absolute; left:50%; top:{px(-20)}px; transform:translateX(-50%);
    color:#f7c53a; font-size:{px(38)}px; background:#2a0b05; padding:0 {px(16)}px;}}
  .date-pill{{position:absolute; top:{px(170)}px; left:{px(350)}px; z-index:6; display:flex; align-items:center; gap:{px(16)}px;
    color:#fff8e8; font-size:{px(32)}px; line-height:1.25; font-weight:900; padding:{px(10)}px {px(24)}px;
    border:{px(2)}px solid #d99a16; border-radius:{px(12)}px; background:rgba(41,7,4,.86);
    box-shadow:0 {px(8)}px {px(18)}px rgba(0,0,0,.34);}}
  .cal{{width:{px(34)}px;height:{px(34)}px;border:{px(3)}px solid #fff4d6;border-radius:{px(5)}px; position:relative;}}
  .cal::before{{content:""; position:absolute; left:{px(5)}px; right:{px(5)}px; top:{px(10)}px; border-top:{px(3)}px solid #fff4d6;}}
  .sage{{position:absolute; left:{px(12)}px; top:{px(190)}px; width:{px(590)}px; height:{px(780)}px; z-index:2; overflow:hidden;}}
  .sage img{{width:100%; height:112%; object-fit:cover; object-position:left bottom; transform:translateY({px(-28)}px);}}
  .zodiac-faint{{position:absolute; left:{px(330)}px; top:{px(275)}px; width:{px(360)}px; height:{px(360)}px;
    border:{px(2)}px solid rgba(232,169,29,.2); border-radius:50%; z-index:1; opacity:.55;}}
  .zodiac-faint::after{{content:"✦  ✧  ✦  ✧  ✦"; position:absolute; inset:{px(60)}px; border:{px(1)}px solid rgba(232,169,29,.18);
    border-radius:50%; color:rgba(232,169,29,.35); font-size:{px(34)}px; display:flex; align-items:center; justify-content:center;}}
  .sign-title{{position:absolute; top:{px(238)}px; right:{px(70)}px; width:{px(470)}px; z-index:5; text-align:center;}}
  .sign-title .tel{{color:#ffe47b; font-size:{px(76)}px; line-height:1.08; font-weight:900;
    text-shadow:0 {px(4)}px 0 #6b3108, 0 {px(10)}px {px(20)}px rgba(0,0,0,.68);}}
  .sign-title .eng{{margin-top:{px(6)}px; color:#fff; font-size:{px(38)}px; line-height:1; font-weight:900; letter-spacing:0;}}
  .ram{{position:absolute; top:{px(390)}px; right:{px(70)}px; width:{px(405)}px; height:{px(390)}px; z-index:4;
    display:flex; align-items:center; justify-content:center;}}
  .ram img{{width:100%; height:100%; object-fit:cover; object-position:center center;}}
  .ram-glyph{{width:{px(315)}px; height:{px(315)}px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    color:#ffd758; font-size:{px(180)}px; border:{px(6)}px solid #ffd758; background:#5c0b07;}}
  .nak{{position:absolute; top:{px(780)}px; right:{px(54)}px; width:{px(500)}px; z-index:5; text-align:center;
    color:#fff7e4; font-size:{px(28)}px; line-height:1.25; font-weight:900; padding:{px(14)}px {px(22)}px;
    background:#5b0d07; border:{px(3)}px solid #f0bd39; border-radius:{px(20)}px;
    box-shadow:0 {px(8)}px {px(20)}px rgba(0,0,0,.35);}}
  .cream{{position:absolute; left:{px(28)}px; right:{px(28)}px; top:{px(970)}px; height:{px(832)}px; z-index:6;
    border:{px(2)}px solid #c88a17; border-radius:{px(22)}px;
    background:linear-gradient(180deg, #fff8df, #fff0c2); box-shadow:0 {px(-7)}px {px(22)}px rgba(0,0,0,.35); overflow:hidden;}}
  .pred-table{{position:absolute; left:{px(28)}px; right:{px(28)}px; top:{px(18)}px; height:{px(468)}px;
    border:{px(1)}px solid #d7a64d; border-radius:{px(22)}px; overflow:hidden;}}
  .pred-row{{height:{px(117)}px; display:grid; grid-template-columns:{px(250)}px 1fr; border-bottom:{px(1)}px solid #d7a64d;}}
  .pred-row:last-child{{border-bottom:0;}}
  .pred-label{{background:linear-gradient(90deg, #3e0804, #5a1108); color:#f7c741; display:flex; align-items:center;
    gap:{px(18)}px; padding:0 {px(26)}px; font-size:{px(34)}px; line-height:1.2; font-weight:900;}}
  .pred-text{{display:flex; align-items:center; padding:{px(8)}px {px(30)}px; color:#2b1208; font-size:{px(25)}px;
    line-height:1.38; font-weight:800; background:rgba(255,255,255,.36);}}
  .icon{{width:{px(48)}px; height:{px(48)}px; position:relative; flex:0 0 auto;}}
  .briefcase{{border:{px(3)}px solid #f0b52d; border-radius:{px(7)}px; background:linear-gradient(#a65b12,#e0a12c);}}
  .briefcase::before{{content:""; position:absolute; left:{px(13)}px; right:{px(13)}px; top:{px(-10)}px; height:{px(12)}px;
    border:{px(3)}px solid #f0b52d; border-bottom:0; border-radius:{px(7)}px {px(7)}px 0 0;}}
  .coins::before,.coins::after{{content:""; position:absolute; border-radius:50%; background:linear-gradient(#ffe071,#c77a04);
    border:{px(2)}px solid #7c4200;}}
  .coins::before{{width:{px(46)}px;height:{px(24)}px;left:0;bottom:{px(6)}px; box-shadow:{px(14)}px {px(-16)}px 0 #e7a91f;}}
  .coins::after{{width:{px(38)}px;height:{px(20)}px;left:{px(6)}px;bottom:{px(23)}px;}}
  .heart::before{{content:"♥"; color:#e31919; -webkit-text-stroke:{px(2)}px #ffd23f; font-size:{px(54)}px; line-height:1;}}
  .cross{{background:#18a750; border:{px(3)}px solid #ffe071; border-radius:{px(10)}px;}}
  .cross::before{{content:"✚"; color:white; font-size:{px(44)}px; line-height:{px(48)}px; text-align:center; display:block;}}
  .cards{{position:absolute; left:{px(28)}px; right:{px(28)}px; bottom:{px(22)}px; display:grid; grid-template-columns:1fr 1.15fr; gap:{px(14)}px;}}
  .card{{height:{px(292)}px; border:{px(1)}px solid #d7a64d; border-radius:{px(18)}px; background:#fff6d8; position:relative;
    padding:{px(64)}px {px(30)}px {px(22)}px; color:#4b1308;}}
  .card-title{{position:absolute; top:{px(12)}px; left:50%; transform:translateX(-50%); min-width:{px(230)}px;
    text-align:center; color:#ffe878; background:#5b0d07; border:{px(2)}px solid #d99a16; border-radius:{px(16)}px;
    padding:{px(7)}px {px(22)}px; font-size:{px(30)}px; line-height:1.2; font-weight:900;}}
  .luck-line{{display:flex; align-items:center; gap:{px(14)}px; font-size:{px(26)}px; line-height:1.55; font-weight:900;}}
  .dot{{width:{px(36)}px;height:{px(36)}px;border-radius:50%;background:#d71912;border:{px(2)}px solid #f5c33c;}}
  .num{{width:{px(36)}px;height:{px(36)}px;border-radius:50%;background:#8b4813;color:#fff2bf;display:flex;align-items:center;justify-content:center;border:{px(2)}px solid #f5c33c;}}
  .star{{color:#f2b51d;font-size:{px(38)}px;line-height:1;}}
  .tip{{text-align:center; font-size:{px(25)}px; line-height:1.55; font-weight:900; padding-top:{px(12)}px;}}
  .tip-art{{position:absolute; bottom:{px(30)}px; width:{px(82)}px; height:{px(82)}px; color:#d37a0a;}}
  .tip-art.left{{left:{px(28)}px;}} .tip-art.right{{right:{px(28)}px;}}
  .tip-art::before{{content:"♜"; font-size:{px(74)}px;}}
  .footer{{position:absolute; left:{px(28)}px; right:{px(28)}px; bottom:{px(14)}px; height:{px(82)}px; z-index:7;
    color:#f6c236; display:flex; align-items:center; justify-content:center; gap:{px(28)}px; font-size:{px(38)}px;
    line-height:1; font-weight:900; text-shadow:0 {px(3)}px {px(8)}px rgba(0,0,0,.72);}}
</style></head><body><div class="poster">
  <div class="corner c1">⌜</div><div class="corner c2">⌜</div><div class="corner c3">⌜</div><div class="corner c4">⌜</div>
  <div class="title">{escape(L["title"])}</div>
  <div class="orn-line"></div>
  <div class="date-pill"><div class="cal"></div><span>{date_text}</span><span>|</span><span>{weekday}</span></div>
  <div class="zodiac-faint"></div>
  <div class="sage">{sage_html}</div>
  <div class="sign-title"><div class="tel">{escape(sign_name)} రాశి</div><div class="eng">({english})</div></div>
  <div class="ram">{ram_html}</div>
  <div class="nak">{nak}</div>
  <div class="cream">
    <div class="pred-table">{rows_html}</div>
    <div class="cards">
      <div class="card">
        <div class="card-title">అదృష్టం</div>
        <div class="luck-line"><span class="dot"></span><span>అదృష్ట రంగు : {escape(color)}</span></div>
        <div class="luck-line"><span class="num">{escape(number)}</span><span>అదృష్ట సంఖ్య : {escape(number)}</span></div>
        <div class="luck-line"><span class="star">★</span><span>అదృష్ట దిక్కు : {escape(direction)}</span></div>
      </div>
      <div class="card">
        <div class="card-title">చిట్కా</div>
        <div class="tip-art left"></div><div class="tip-art right"></div>
        <div class="tip">{escape(details.get("deity", ""))}ని ఆరాధించండి.<br>{escape(details.get("mantra", ""))} అని<br>11 సార్లు జపించండి.</div>
      </div>
    </div>
  </div>
  <div class="footer"><span>◄</span><span>✤</span><span>{escape(L["blessing"])}</span><span>✤</span><span>►</span></div>
</div></body></html>"""


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
        sign = _base_sign(channel)
        language = self.language_for(channel)
        n, color, mood = _daily_highlights(sign, today.isoformat())
        if language == "telugu" and sign == "aries":
            n, color = 7, "Red"
        display, glyph, date_range = _sign(sign)
        localized_date, weekday = _localized_date(today, language)
        data = {
            "channel": channel,
            "sign": sign,
            "sign_display": display,
            "glyph": glyph,
            "date_range": date_range,
            "date": today.strftime("%d %b %Y"),
            "localized_date": localized_date,
            "weekday": weekday,
            "lucky_number": n,
            "lucky_color": color,
            "mood": mood,
        }
        if language == "telugu":
            data["sign_details"] = _SIGN_DETAILS.get(sign, {})
            data["predictions"] = _daily_predictions(sign, today.isoformat())
        return data

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
        predictions = data.get("predictions") or {}
        details = data.get("sign_details") or {}
        data_block = (
            f"Zodiac sign: {disp} ({data['date_range']})\n"
            f"Date: {data['date']}\n"
            f"Lucky number: {n}\nLucky colour: {color}\nMood today: {mood}"
        )
        if predictions:
            data_block += (
                "\nStructured guidance shown on card:\n"
                f"- Career/work: {predictions.get('career', '')}\n"
                f"- Finance: {predictions.get('finance', '')}\n"
                f"- Love/family: {predictions.get('love', '')}\n"
                f"- Health/wellness: {predictions.get('health', '')}"
            )
        if details:
            data_block += (
                "\nDevotional/remedy details shown on card:\n"
                f"- Nakshatra/pada: {details.get('nakshatra', '')}\n"
                f"- Deity: {details.get('deity', '')}\n"
                f"- Mantra: {details.get('mantra', '')}\n"
                f"- Lucky direction: {details.get('direction', '')}"
            )
        if variant == "long":
            instructions = [
                f"Say this is today's horoscope for {disp}.",
                "Use the same four guidance blocks shown on the card: career/work, finance, love/family, and health/wellness. "
                "Keep them warm, encouraging, and GENERAL.",
                f"Naturally mention the lucky number ({n}), lucky colour ({color}), and the mood ({mood}).",
                "Mention the devotional remedy details briefly only as a cultural/devotional suggestion, not as a guarantee.",
                "Do NOT make specific or guaranteed predictions about health, money, marriage, or exam results.",
            ]
        else:
            instructions = [
                f"Say this is today's horoscope for {disp}.",
                f"Give 2-3 short, upbeat lines using the same card guidance, and mention the lucky number ({n}) and lucky colour ({color}).",
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
