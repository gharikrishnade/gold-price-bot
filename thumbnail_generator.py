"""
thumbnail_generator.py — Bold & Bright thumbnail via HTML + Playwright

PRIMARY:  HTML rendered by Chromium (Playwright) — correct Indic script shaping via HarfBuzz
FALLBACK: PIL — WARNING: PIL cannot shape Telugu/Tamil/etc correctly (garbled glyphs)

Install Playwright once:
    pip install playwright
    playwright install chromium
"""

import logging
import tempfile
import os
import shutil
import subprocess
from pathlib import Path
from datetime import date

logger = logging.getLogger(__name__)

# ── Language data ─────────────────────────────────────────────────────────────
LANG_STRINGS = {
    "telugu":    {"title": "నేటి బంగారం ధర",        "native": "తెలుగు",   "c22": "22 కెరట్",  "c24": "24 కెరట్",  "font": "Kohinoor Telugu, Telugu MN, Telugu Sangam MN, Noto Sans Telugu"},
    "tamil":     {"title": "இன்றைய தங்கம் விலை",   "native": "தமிழ்",    "c22": "22 கேரட்",  "c24": "24 கேரட்",  "font": "Tamil MN, Tamil Sangam MN, Noto Sans Tamil"},
    "kannada":   {"title": "ಇಂದಿನ ಚಿನ್ನದ ಬೆಲೆ",    "native": "ಕನ್ನಡ",   "c22": "22 ಕ್ಯಾರಟ್","c24": "24 ಕ್ಯಾರಟ್","font": "Kannada MN, Kannada Sangam MN, Noto Sans Kannada"},
    "malayalam": {"title": "ഇന്നത്തെ സ്വർണ്ണ വില", "native": "മലയാളം",  "c22": "22 കാരറ്റ്","c24": "24 കാരറ്റ്","font": "Malayalam MN, Malayalam Sangam MN, Noto Sans Malayalam"},
    "hindi":     {"title": "आज का सोने का भाव",      "native": "हिंदी",    "c22": "22 कैरेट",  "c24": "24 कैरेट",  "font": "Kohinoor Devanagari, Devanagari Sangam MN, Devanagari MT, Noto Sans Devanagari"},
    "marathi":   {"title": "आजचा सोन्याचा भाव",     "native": "मराठी",   "c22": "22 कॅरेट",  "c24": "24 कॅरेट",  "font": "Kohinoor Devanagari, Devanagari Sangam MN, Devanagari MT, Noto Sans Devanagari"},
    "bengali":   {"title": "আজকের সোনার দাম",        "native": "বাংলা",   "c22": "22 ক্যারেট","c24": "24 ক্যারেট","font": "Bangla MN, Bangla Sangam MN, Noto Sans Bengali"},
}

FONT_CANDIDATES = {
    "telugu": ["Noto Sans Telugu", "Kohinoor Telugu", "Telugu MN", "Telugu Sangam MN"],
    "tamil": ["Noto Sans Tamil", "Tamil MN", "Tamil Sangam MN"],
    "kannada": ["Noto Sans Kannada", "Kannada MN", "Kannada Sangam MN"],
    "malayalam": ["Noto Sans Malayalam", "Malayalam MN", "Malayalam Sangam MN"],
    "hindi": ["Noto Sans Devanagari", "Kohinoor Devanagari", "Devanagari Sangam MN", "Devanagari MT"],
    "marathi": ["Noto Sans Devanagari", "Kohinoor Devanagari", "Devanagari Sangam MN", "Devanagari MT"],
    "bengali": ["Noto Sans Bengali", "Bangla MN", "Bangla Sangam MN"],
}

SYSTEM_FONT_FILES = {
    "Kohinoor Telugu": ["/System/Library/Fonts/KohinoorTelugu.ttc"],
    "Telugu MN": ["/System/Library/Fonts/Supplemental/Telugu MN.ttc"],
    "Telugu Sangam MN": ["/System/Library/Fonts/Supplemental/Telugu Sangam MN.ttc"],
    "Tamil MN": ["/System/Library/Fonts/Supplemental/Tamil MN.ttc"],
    "Tamil Sangam MN": ["/System/Library/Fonts/Supplemental/Tamil Sangam MN.ttc"],
    "Kannada MN": ["/System/Library/Fonts/Kannada MN.ttc", "/System/Library/Fonts/KannadaMN.ttc"],
    "Kannada Sangam MN": ["/System/Library/Fonts/Supplemental/Kannada Sangam MN.ttc"],
    "Malayalam MN": ["/System/Library/Fonts/Malayalam MN.ttc", "/System/Library/Fonts/MalayalamMN.ttc"],
    "Malayalam Sangam MN": ["/System/Library/Fonts/Supplemental/Malayalam Sangam MN.ttc"],
    "Kohinoor Devanagari": ["/System/Library/Fonts/Kohinoor.ttc", "/System/Library/Fonts/KohinoorDevanagari.ttc"],
    "Devanagari Sangam MN": ["/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"],
    "Devanagari MT": ["/System/Library/Fonts/Supplemental/DevanagariMT.ttc"],
    "Bangla MN": ["/System/Library/Fonts/Bangla MN.ttc", "/System/Library/Fonts/BanglaMN.ttc"],
    "Bangla Sangam MN": ["/System/Library/Fonts/Supplemental/Bangla Sangam MN.ttc"],
}

STATE_DISPLAY = {
    "andhra_pradesh": "Andhra Pradesh",
    "telangana":      "Telangana",
    "tamil_nadu":     "Tamil Nadu",
    "karnataka":      "Karnataka",
    "kerala":         "Kerala",
    "maharashtra":    "Maharashtra",
    "west_bengal":    "West Bengal",
    "uttar_pradesh":  "Uttar Pradesh",
    "rajasthan":      "Rajasthan",
    "gujarat":        "Gujarat",
    "punjab":         "Punjab",
}

CITY_NAMES = {
    "telugu":    {"Hyderabad": "హైదరాబాద్", "Warangal": "వరంగల్", "Vijayawada": "విజయవాడ", "Visakhapatnam": "విశాఖపట్నం", "Guntur": "గుంటూరు", "Tirupati": "తిరుపతి"},
    "tamil":     {"Chennai": "சென்னை", "Coimbatore": "கோயம்புத்தூர்", "Madurai": "மதுரை", "Salem": "சேலம்"},
    "kannada":   {"Bangalore": "ಬೆಂಗಳೂರು", "Bengaluru": "ಬೆಂಗಳೂರು", "Mysore": "ಮೈಸೂರು", "Hubli": "ಹುಬ್ಬಳ್ಳಿ"},
    "malayalam": {"Thiruvananthapuram": "തിരുവനന്തപുരം", "Kochi": "കൊച്ചി", "Kozhikode": "കോഴിക്കോട്"},
    "hindi":     {"Delhi": "दिल्ली", "Mumbai": "मुंबई", "Lucknow": "लखनऊ"},
    "marathi":   {"Mumbai": "मुंबई", "Pune": "पुणे", "Nagpur": "नागपूर"},
    "bengali":   {"Kolkata": "কলকাতা", "Howrah": "হাওড়া", "Asansol": "আসানসোল"},
}


def check_required_fonts(languages: list[str]) -> dict:
    """Return installed/missing font candidates for thumbnail languages."""
    results = {}
    for language in sorted(set(languages)):
        candidates = FONT_CANDIDATES.get(language, FONT_CANDIDATES["hindi"])
        installed = [font for font in candidates if _font_available(font)]
        results[language] = {
            "ok": bool(installed),
            "installed": installed,
            "required_any_of": candidates,
        }
    return results


def _font_available(font_name: str) -> bool:
    for path in SYSTEM_FONT_FILES.get(font_name, []):
        if Path(path).exists():
            return True

    fc_match = shutil.which("fc-match")
    if fc_match:
        try:
            result = subprocess.run(
                [fc_match, font_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (result.stdout or "").lower()
            return result.returncode == 0 and font_name.lower().split()[0] in output
        except Exception:
            return False
    return False


def ensure_language_font(language: str) -> dict:
    result = check_required_fonts([language])[language]
    if not result["ok"]:
        required = ", ".join(result["required_any_of"])
        raise RuntimeError(
            f"Missing thumbnail font for {language}. Install one of: {required}. "
            "On Ubuntu, install fonts-noto-core and fonts-noto-extra."
        )
    logger.info(
        f"Thumbnail font check passed for {language}: {', '.join(result['installed'])}"
    )
    return result


def _fit_font_size(text: str, base_size: int, min_size: int, soft_limit: int) -> int:
    if len(text) <= soft_limit:
        return base_size
    overflow = len(text) - soft_limit
    return max(min_size, base_size - overflow * 2)


def _css_font_stack(font_stack: str) -> str:
    return ", ".join(f"'{font.strip()}'" for font in font_stack.split(",") if font.strip())


def _build_html(language, state_key, price_data, width, height):
    s = LANG_STRINGS.get(language, LANG_STRINGS["hindi"])
    sc = width / 1280   # scale factor

    cities_data = price_data.get("cities", {})
    primary     = next(iter(cities_data), "")
    prices      = cities_data.get(primary, {})
    p22g   = prices.get("22k_per_gram", 0)
    p24g   = prices.get("24k_per_gram", 0)
    p22_10 = prices.get("22k_per_10g",  0)
    p24_10 = prices.get("24k_per_10g",  0)
    date_str   = price_data.get("date", date.today().strftime("%d %b %Y"))
    city_keys  = list(cities_data.keys())[:3]

    city_trans = CITY_NAMES.get(language, {})
    city_names = [city_trans.get(c, c) for c in city_keys]
    cities_text = "  ·  ".join(city_names)

    subtitle = "Today's Gold Rate — " + STATE_DISPLAY.get(state_key, state_key.replace("_", " ").title())

    regional_font = _css_font_stack(s["font"])
    title_font_size = _fit_font_size(s["title"], 70, 48, 18)
    subtitle_font_size = _fit_font_size(subtitle, 19, 15, 38)
    cities_font_size = _fit_font_size(cities_text, 22, 15, 36)

    def px(n): return f"{int(n * sc)}px"

    html = f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {width}px; height: {height}px; overflow: hidden;
    font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif;
    background: #111827;
  }}

  .wrapper {{
    display: flex;
    width: {width}px;
    height: {height}px;
    background:
      linear-gradient(120deg, rgba(17,24,39,.96), rgba(17,24,39,.9)),
      repeating-linear-gradient(74deg, rgba(59,130,246,.16) 0 1px, transparent 1px {px(96)});
  }}

  /* ── LEFT COLUMN ── */
  .left {{
    width: {px(265)};
    height: {height}px;
    background: #0b1020;
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
    border-right: {px(3)} solid #334155;
  }}

  .coin-area {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: {px(14)};
  }}

  .coin {{
    width: {px(144)}; height: {px(144)};
    border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, #FFE070 0%, #DAA520 45%, #8B6400 100%);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 {px(4)} {px(18)} rgba(0,0,0,0.7), inset 0 -{px(2)} {px(6)} rgba(0,0,0,0.4);
    position: relative;
  }}
  .coin-inner {{
    width: {px(112)}; height: {px(112)};
    border-radius: 50%;
    background: radial-gradient(circle at 35% 35%, #FFF0A0 0%, #C8900A 55%, #7A5500 100%);
    display: flex; align-items: center; justify-content: center;
    position: relative;
  }}
  .coin-shine {{
    position: absolute;
    top: {px(10)}; left: {px(14)};
    width: {px(22)}; height: {px(22)};
    border-radius: 50%;
    background: rgba(255,255,210,0.75);
  }}
  .coin-rupee {{
    font-size: {px(56)};
    font-weight: 900;
    color: #FFE878;
    text-shadow: {px(2)} {px(2)} {px(4)} rgba(0,0,0,0.5);
    line-height: 1;
    position: relative;
    z-index: 1;
  }}

  .gold-label {{
    font-size: {px(15)};
    font-weight: 900;
    color: #f6c453;
    letter-spacing: {px(1)};
    text-align: center;
  }}
  .lang-native {{
    font-family: {regional_font}, sans-serif;
    font-size: {px(17)};
    color: #94a3b8;
    text-align: center;
  }}

  .date-box {{
    width: 100%;
    background: #1f2937;
    text-align: center;
    padding: {px(14)} {px(8)} {px(18)};
    border-top: {px(2)} solid #334155;
  }}
  .date-label {{
    font-size: {px(12)};
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: {px(2)};
    margin-bottom: {px(4)};
  }}
  .date-value {{
    font-size: {px(20)};
    font-weight: 900;
    color: #f6c453;
  }}

  /* ── RIGHT AREA ── */
  .right {{
    flex: 1;
    display: flex;
    flex-direction: column;
    background: transparent;
  }}

  .content {{
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: {px(18)} {px(18)} 0;
  }}

  .title-block {{
    text-align: center;
    margin-bottom: {px(10)};
    min-height: {px(96)};
    display: flex;
    flex-direction: column;
    justify-content: center;
  }}
  .main-title {{
    font-family: {regional_font}, sans-serif;
    font-size: {px(title_font_size)};
    font-weight: 700;
    color: #fff7db;
    line-height: 1.1;
    margin-bottom: {px(4)};
    max-width: 100%;
    overflow-wrap: anywhere;
    text-wrap: balance;
  }}
  .sub-title {{
    font-size: {px(subtitle_font_size)};
    font-weight: 600;
    color: #cbd5e1;
    max-width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .divider {{
    height: {px(2)};
    background: linear-gradient(to right, transparent, #334155 30%, #334155 70%, transparent);
    margin-bottom: {px(12)};
  }}

  /* ── CARDS ── */
  .cards {{
    display: flex;
    gap: {px(18)};
    flex: 1;
    min-height: 0;
  }}

  .card {{
    flex: 1;
    min-width: 0;
    border-radius: {px(20)};
    display: flex;
    flex-direction: column;
    align-items: center;
    overflow: hidden;
    padding-bottom: {px(18)};
    border: {px(2)} solid #475569;
    box-shadow: 0 {px(18)} {px(30)} rgba(0,0,0,.35);
  }}
  .card-22 {{ background: rgba(31,41,55,.96); }}
  .card-24 {{ background: rgba(31,41,55,.96); }}

  .card-bar {{
    width: 100%; height: {px(8)};
    flex-shrink: 0;
    margin-bottom: {px(14)};
  }}
  .card-22 .card-bar {{ background: #22c55e; }}
  .card-24 .card-bar {{ background: #f59e0b; }}

  .carat-lbl {{
    font-size: {px(24)};
    font-weight: 900;
    letter-spacing: {px(2)};
    margin-bottom: {px(8)};
  }}
  .card-22 .carat-lbl {{ color: #22c55e; }}
  .card-24 .carat-lbl {{ color: #f59e0b; }}

  .price-num {{
    font-size: clamp({px(72)}, {px(96)}, {px(96)});
    font-weight: 900;
    color: #FFFFFF;
    letter-spacing: 0;
    line-height: 1;
    margin-bottom: {px(4)};
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .per-gram {{
    font-size: {px(22)};
    font-weight: 700;
    margin-bottom: {px(12)};
  }}
  .card-22 .per-gram {{ color: #22c55e; }}
  .card-24 .per-gram {{ color: #f59e0b; }}

  .card-sep {{
    width: calc(100% - {px(40)});
    height: 1px;
    margin-bottom: {px(12)};
  }}
  .card-22 .card-sep {{ background: rgba(148,163,184,0.25); }}
  .card-24 .card-sep {{ background: rgba(148,163,184,0.25); }}

  .price-10g {{
    font-size: {px(22)};
    font-weight: 600;
    margin-bottom: {px(6)};
    text-align: center;
    max-width: calc(100% - {px(24)});
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .card-22 .price-10g {{ color: #cbd5e1; }}
  .card-24 .price-10g {{ color: #cbd5e1; }}

  .grade-lbl {{
    font-family: {regional_font}, sans-serif;
    font-size: {px(17)};
    max-width: calc(100% - {px(24)});
    text-align: center;
    overflow-wrap: anywhere;
  }}
  .card-22 .grade-lbl {{ color: #94a3b8; }}
  .card-24 .grade-lbl {{ color: #94a3b8; }}

  /* ── BOTTOM BAR ── */
  .bottom-bar {{
    background: #0f172a;
    height: {px(78)};
    display: flex;
    align-items: center;
    padding: 0 {px(16)} 0 {px(20)};
    border-top: {px(2)} solid #334155;
    flex-shrink: 0;
    gap: {px(12)};
  }}
  .cities {{
    font-family: {regional_font}, sans-serif;
    font-size: {px(cities_font_size)};
    color: #f6c453;
    flex: 1;
    min-width: 0;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .sub-btn {{
    background: #f6c453;
    color: #111827;
    border-radius: {px(8)};
    padding: {px(10)} {px(18)};
    font-size: {px(16)};
    font-weight: 900;
    letter-spacing: 0.5px;
    white-space: nowrap;
    flex-shrink: 0;
  }}
</style>
</head>
<body>
<div class="wrapper">

  <div class="left">
    <div class="coin-area">
      <div class="coin">
        <div class="coin-inner">
          <div class="coin-shine"></div>
          <span class="coin-rupee">₹</span>
        </div>
      </div>
      <div class="gold-label">GOLD UPDATES</div>
      <div class="lang-native">{s['native']}</div>
    </div>
    <div class="date-box">
      <div class="date-label">DATE</div>
      <div class="date-value">{date_str}</div>
    </div>
  </div>

  <div class="right">
    <div class="content">
      <div class="title-block">
        <div class="main-title">{s['title']}</div>
        <div class="sub-title">{subtitle}</div>
      </div>
      <div class="divider"></div>
      <div class="cards">

        <div class="card card-22">
          <div class="card-bar"></div>
          <div class="carat-lbl">22 CARAT</div>
          <div class="price-num">{p22g:,}</div>
          <div class="per-gram">₹&nbsp; per gram</div>
          <div class="card-sep"></div>
          <div class="price-10g">₹{p22_10:,} &nbsp;/&nbsp; 10 grams</div>
          <div class="grade-lbl">{s['c22']} &nbsp;·&nbsp; Jewellery</div>
        </div>

        <div class="card card-24">
          <div class="card-bar"></div>
          <div class="carat-lbl">24 CARAT</div>
          <div class="price-num">{p24g:,}</div>
          <div class="per-gram">₹&nbsp; per gram</div>
          <div class="card-sep"></div>
          <div class="price-10g">₹{p24_10:,} &nbsp;/&nbsp; 10 grams</div>
          <div class="grade-lbl">{s['c24']} &nbsp;·&nbsp; Investment</div>
        </div>

      </div>
    </div>
    <div class="bottom-bar">
      <div class="cities">{cities_text}</div>
      <div class="sub-btn">▶&nbsp; SUBSCRIBE</div>
    </div>
  </div>

</div>
</body>
</html>"""
    return html


def _build_vertical_html(language, state_key, price_data, width, height):
    """Portrait 9:16 template for Shorts/Reels — header + two stacked carat cards + footer."""
    s = LANG_STRINGS.get(language, LANG_STRINGS["hindi"])
    sc = width / 1080   # scale factor (portrait reference width)

    cities_data = price_data.get("cities", {})
    primary     = next(iter(cities_data), "")
    prices      = cities_data.get(primary, {})
    p22g   = prices.get("22k_per_gram", 0)
    p24g   = prices.get("24k_per_gram", 0)
    p22_10 = prices.get("22k_per_10g",  0)
    p24_10 = prices.get("24k_per_10g",  0)
    date_str   = price_data.get("date", date.today().strftime("%d %b %Y"))
    city_keys  = list(cities_data.keys())[:3]

    city_trans = CITY_NAMES.get(language, {})
    city_names = [city_trans.get(c, c) for c in city_keys]
    cities_text = "  ·  ".join(city_names)

    subtitle = "Today's Gold Rate — " + STATE_DISPLAY.get(state_key, state_key.replace("_", " ").title())

    regional_font = _css_font_stack(s["font"])
    title_font_size = _fit_font_size(s["title"], 92, 58, 15)
    cities_font_size = _fit_font_size(cities_text, 30, 20, 34)

    def px(n): return f"{int(n * sc)}px"

    def card(kind, carat_native, carat_en, pg, p10, grade):
        return f"""
        <div class="vcard vcard-{kind}">
          <div class="vcard-bar"></div>
          <div class="vcard-body">
            <div class="vcarat">{carat_en}</div>
            <div class="vprice">{pg:,}</div>
            <div class="vpergram">₹&nbsp; per gram</div>
            <div class="vsep"></div>
            <div class="v10g">₹{p10:,} &nbsp;/&nbsp; 10 grams</div>
            <div class="vgrade">{carat_native}</div>
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {width}px; height: {height}px; overflow: hidden;
    font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif;
    background:
      linear-gradient(160deg, #111827 0%, #0b1020 100%),
      repeating-linear-gradient(74deg, rgba(59,130,246,.10) 0 1px, transparent 1px {px(120)});
  }}
  .vwrap {{
    width: {width}px; height: {height}px;
    display: flex; flex-direction: column;
    padding: {px(70)} {px(54)} {px(54)};
    gap: {px(34)};
  }}

  /* ── HEADER ── */
  .vhead {{ text-align: center; display: flex; flex-direction: column; align-items: center; gap: {px(16)}; }}
  .vcoin {{
    width: {px(150)}; height: {px(150)}; border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, #FFE070 0%, #DAA520 45%, #8B6400 100%);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 {px(6)} {px(22)} rgba(0,0,0,0.7), inset 0 -{px(3)} {px(8)} rgba(0,0,0,0.4);
  }}
  .vcoin span {{ font-size: {px(74)}; font-weight: 900; color: #FFE878; text-shadow: {px(2)} {px(2)} {px(4)} rgba(0,0,0,0.5); }}
  .vgold-label {{ font-size: {px(22)}; font-weight: 900; color: #f6c453; letter-spacing: {px(3)}; }}
  .vtitle {{
    font-family: {regional_font}, sans-serif;
    font-size: {px(title_font_size)}; font-weight: 700; color: #fff7db;
    line-height: 1.12; overflow-wrap: anywhere; text-wrap: balance;
  }}
  .vsub {{ font-size: {px(30)}; font-weight: 600; color: #cbd5e1; }}
  .vdate-top {{
    margin-top: {px(6)};
    display: inline-flex; align-items: center; align-self: center;
    background: #1f2937; border: {px(2)} solid #334155; border-radius: {px(40)};
    padding: {px(10)} {px(24)};
    font-size: {px(26)}; font-weight: 800; color: #f6c453; letter-spacing: {px(1)};
  }}

  /* ── CARDS (stacked) ── */
  .vcards {{ flex: 1; display: flex; flex-direction: column; gap: {px(34)}; min-height: 0; }}
  .vcard {{
    flex: 1; border-radius: {px(30)}; overflow: hidden;
    background: rgba(31,41,55,.96);
    border: {px(3)} solid #475569;
    box-shadow: 0 {px(20)} {px(40)} rgba(0,0,0,.4);
    display: flex; flex-direction: column;
  }}
  .vcard-bar {{ width: 100%; height: {px(14)}; flex-shrink: 0; }}
  .vcard-22 .vcard-bar {{ background: #22c55e; }}
  .vcard-24 .vcard-bar {{ background: #f59e0b; }}
  .vcard-body {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: {px(20)}; }}
  .vcarat {{ font-size: {px(40)}; font-weight: 900; letter-spacing: {px(3)}; margin-bottom: {px(10)}; }}
  .vcard-22 .vcarat {{ color: #22c55e; }}
  .vcard-24 .vcarat {{ color: #f59e0b; }}
  .vprice {{ font-size: {px(150)}; font-weight: 900; color: #FFFFFF; line-height: 1; margin-bottom: {px(8)}; }}
  .vpergram {{ font-size: {px(34)}; font-weight: 700; margin-bottom: {px(18)}; }}
  .vcard-22 .vpergram {{ color: #22c55e; }}
  .vcard-24 .vpergram {{ color: #f59e0b; }}
  .vsep {{ width: 60%; height: 1px; background: rgba(148,163,184,0.28); margin-bottom: {px(18)}; }}
  .v10g {{ font-size: {px(34)}; font-weight: 600; color: #cbd5e1; margin-bottom: {px(8)}; }}
  .vgrade {{ font-family: {regional_font}, sans-serif; font-size: {px(28)}; color: #94a3b8; }}

  /* ── FOOTER ── */
  .vfoot {{
    flex-shrink: 0; background: #0f172a; border-radius: {px(20)};
    border: {px(2)} solid #334155;
    padding: {px(22)} {px(28)};
    display: flex; flex-direction: column; align-items: center; gap: {px(14)};
  }}
  .vcities {{
    font-family: {regional_font}, sans-serif; font-size: {px(cities_font_size)};
    color: #f6c453; font-weight: 700; text-align: center;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;
  }}
  .vsub-btn {{
    background: #f6c453; color: #111827; border-radius: {px(10)};
    padding: {px(14)} {px(26)}; font-size: {px(26)}; font-weight: 900; white-space: nowrap;
  }}
</style>
</head>
<body>
<div class="vwrap">

  <div class="vhead">
    <div class="vcoin"><span>₹</span></div>
    <div class="vgold-label">GOLD UPDATES &nbsp;·&nbsp; {s['native']}</div>
    <div class="vtitle">{s['title']}</div>
    <div class="vsub">{subtitle}</div>
    <div class="vdate-top">{date_str}</div>
  </div>

  <div class="vcards">
    {card("22", s['c22'] + " · Jewellery", "22 CARAT", p22g, p22_10, "")}
    {card("24", s['c24'] + " · Investment", "24 CARAT", p24g, p24_10, "")}
  </div>

  <div class="vfoot">
    <div class="vcities">{cities_text}</div>
    <div class="vsub-btn">▶&nbsp; SUBSCRIBE</div>
  </div>

</div>
</body>
</html>"""
    return html


def generate_vertical_thumbnail(
    language: str,
    state_key: str,
    price_data: dict,
    output_path: str,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Render the portrait 9:16 Shorts/Reels frame via Playwright (Chromium)."""
    html = _build_vertical_html(language, state_key, price_data, width, height)
    _render_playwright(html, output_path, width, height)
    return output_path


def _render_playwright(html, output_path, width, height):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        # Give fonts a moment to load
        page.wait_for_timeout(500)
        page.screenshot(path=output_path, type="jpeg", quality=95,
                        clip={"x": 0, "y": 0, "width": width, "height": height})
        browser.close()
    logger.info(f"Thumbnail saved via Playwright ({width}×{height}): {output_path}")


def generate_thumbnail(
    language: str,
    state_key: str,
    price_data: dict,
    output_path: str,
    width: int = 1280,
    height: int = 720,
) -> str:
    """
    Generate a Bold & Bright thumbnail.
    Uses Playwright (Chromium) for correct Indic script rendering.
    Falls back to PIL if Playwright is not installed.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    ensure_language_font(language)
    html = _build_html(language, state_key, price_data, width, height)

    try:
        _render_playwright(html, output_path, width, height)
        return output_path
    except ImportError:
        logger.warning("Playwright not installed — falling back to PIL (Indic fonts will be garbled)")
        logger.warning("Fix: pip install playwright && playwright install chromium")
        return _render_pil_fallback(language, state_key, price_data, output_path, width, height)
    except Exception as e:
        logger.error(f"Playwright render failed: {e}")
        raise


def _render_pil_fallback(language, state_key, price_data, output_path, width, height):
    """PIL fallback — correct layout but Indic text may not render properly."""
    from PIL import Image, ImageDraw, ImageFont

    def _find(*paths):
        for p in paths:
            if Path(p).exists():
                return str(p)
        return None

    latin = _find("/System/Library/Fonts/Helvetica.ttc",
                  "/System/Library/Fonts/Arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    regional_map = {
        "telugu":    _find("/System/Library/Fonts/KohinoorTelugu.ttc",    "/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf"),
        "tamil":     _find("/System/Library/Fonts/KohinoorTamil.ttc",     "/usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf"),
        "kannada":   _find("/System/Library/Fonts/KannadaMN.ttc",         "/usr/share/fonts/truetype/noto/NotoSansKannada-Bold.ttf"),
        "malayalam": _find("/System/Library/Fonts/MalayalamMN.ttc",       "/usr/share/fonts/truetype/noto/NotoSansMalayalam-Bold.ttf"),
        "hindi":     _find("/System/Library/Fonts/KohinoorDevanagari.ttc","/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
        "marathi":   _find("/System/Library/Fonts/KohinoorDevanagari.ttc","/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
        "bengali":   _find("/System/Library/Fonts/BanglaMN.ttc",          "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf"),
    }
    reg = regional_map.get(language, latin)

    def fnt(path, size):
        try: return ImageFont.truetype(path, size)
        except: return ImageFont.load_default()

    sc = width / 1280
    s = LANG_STRINGS.get(language, LANG_STRINGS["hindi"])
    cities_data = price_data.get("cities", {})
    primary = next(iter(cities_data), "")
    prices  = cities_data.get(primary, {})
    p22g, p24g = prices.get("22k_per_gram",0), prices.get("24k_per_gram",0)
    p22_10, p24_10 = prices.get("22k_per_10g",0), prices.get("24k_per_10g",0)
    date_str = price_data.get("date", date.today().strftime("%d %b %Y"))
    city_keys = list(cities_data.keys())[:3]
    city_trans = CITY_NAMES.get(language, {})
    city_names = [city_trans.get(c, c) for c in city_keys]

    lw = int(265*sc); bh = int(78*sc)
    img = Image.new("RGB", (width, height), (17,24,39))
    draw = ImageDraw.Draw(img)
    for y in range(height-bh):
        t = y/max(1,height-bh)
        draw.line([(lw,y),(width,y)], fill=(int(17+5*t),int(24+10*t),int(39+15*t)))
    draw.rectangle([(0,0),(lw,height)], fill=(11,16,32))
    draw.rectangle([(lw-3,0),(lw,height-bh)], fill=(51,65,85))
    # title
    cx = lw+(width-lw)//2
    draw.text((cx,int(62*sc)), s["title"], font=fnt(reg,int(70*sc)), fill=(255,247,219), anchor="mm")
    subtitle = "Today's Gold Rate — "+STATE_DISPLAY.get(state_key, state_key.replace("_"," ").title())
    draw.text((cx,int(108*sc)), subtitle, font=fnt(latin,int(19*sc)), fill=(203,213,225), anchor="mm")
    draw.line([(lw+int(18*sc),int(124*sc)),(width-int(18*sc),int(124*sc))], fill=(51,65,85), width=2)
    # cards
    gap=int(18*sc); cy=int(134*sc); ch=int(500*sc)
    cw=(width-lw-gap*3)//2; x22=lw+gap; x24=x22+cw+gap
    for x,bg,acc,lbl,p,p10,cs in [
        (x22,(31,41,55),(34,197,94),"22 CARAT",p22g,p22_10,s["c22"]),
        (x24,(31,41,55),(245,158,11),"24 CARAT",p24g,p24_10,s["c24"]),
    ]:
        draw.rounded_rectangle([(x,cy),(x+cw,cy+ch)], radius=int(14*sc), fill=bg)
        draw.rounded_rectangle([(x,cy),(x+cw,cy+int(8*sc))], radius=int(5*sc), fill=acc)
        m = x+cw//2
        draw.text((m,cy+int(38*sc)), lbl, font=fnt(latin,int(24*sc)), fill=acc, anchor="mm")
        draw.text((m,cy+int(175*sc)), f"{p:,}", font=fnt(latin,int(96*sc)), fill=(255,255,255), anchor="mm")
        draw.text((m,cy+int(245*sc)), "₹ per gram", font=fnt(latin,int(22*sc)), fill=acc, anchor="mm")
        draw.line([(x+int(28*sc),cy+int(272*sc)),(x+cw-int(28*sc),cy+int(272*sc))], fill=(71,85,105), width=1)
        draw.text((m,cy+int(315*sc)), f"₹{p10:,} / 10 grams", font=fnt(latin,int(22*sc)), fill=(203,213,225), anchor="mm")
        draw.text((m,cy+int(360*sc)), f"{cs} · Jewellery" if "22" in lbl else f"{cs} · Investment", font=fnt(reg,int(17*sc)), fill=(148,163,184), anchor="mm")
    # bottom
    by=height-bh
    draw.rectangle([(lw,by),(width,height)], fill=(15,23,42))
    draw.line([(lw,by),(width,by)], fill=(51,65,85), width=2)
    draw.text(((lw+width-int(160*sc))//2,by+bh//2), "  ·  ".join(city_names), font=fnt(reg,int(22*sc)), fill=(246,196,83), anchor="mm")
    bw,bhh=int(150*sc),int(38*sc)
    bx=width-bw-int(14*sc); bby=by+(bh-bhh)//2
    draw.rounded_rectangle([(bx,bby),(bx+bw,bby+bhh)], radius=int(7*sc), fill=(246,196,83))
    draw.text((bx+bw//2,bby+bhh//2), "▶  SUBSCRIBE", font=fnt(latin,int(16*sc)), fill=(17,24,39), anchor="mm")
    # date box
    dbh=int(86*sc); dby=height-bh-dbh
    draw.rectangle([(0,dby),(lw-3,height-bh)], fill=(31,41,55))
    draw.line([(0,dby),(lw-3,dby)], fill=(51,65,85), width=2)
    draw.text((lw//2,dby+int(18*sc)), "DATE", font=fnt(latin,int(12*sc)), fill=(148,163,184), anchor="mm")
    draw.text((lw//2,dby+int(52*sc)), date_str, font=fnt(latin,int(20*sc)), fill=(246,196,83), anchor="mm")
    # coin
    coin_r=int(72*sc); ccx=lw//2; ccy=int(248*sc)
    draw.ellipse([(ccx-coin_r,ccy-coin_r),(ccx+coin_r,ccy+coin_r)], fill=(160,110,5))
    draw.ellipse([(ccx-int(coin_r*.88),ccy-int(coin_r*.88)),(ccx+int(coin_r*.88),ccy+int(coin_r*.88))], fill=(218,165,32))
    draw.ellipse([(ccx-int(coin_r*.70),ccy-int(coin_r*.70)),(ccx+int(coin_r*.70),ccy+int(coin_r*.70))], fill=(140,95,0))
    draw.text((ccx,ccy+int(coin_r*.06)), "₹", font=fnt(latin,int(coin_r*.75)), fill=(255,235,100), anchor="mm")
    draw.text((lw//2,ccy+coin_r+int(20*sc)), "GOLD UPDATES", font=fnt(latin,int(14*sc)), fill=(246,196,83), anchor="mm")
    draw.text((lw//2,ccy+coin_r+int(40*sc)), s["native"], font=fnt(reg,int(16*sc)), fill=(148,163,184), anchor="mm")

    img.save(output_path, "JPEG", quality=95)
    logger.info(f"Thumbnail saved via PIL fallback ({width}×{height}): {output_path}")
    return output_path


# ── Batch helper ──────────────────────────────────────────────────────────────
def generate_all_thumbnails(all_price_data: dict, output_dir: str = "output/thumbnails") -> dict:
    from config import CHANNEL_CONFIG
    today_str = date.today().isoformat()
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = {}
    for state_key, config in CHANNEL_CONFIG.items():
        if not config.get("enabled"):
            continue
        language = config["language"]
        state_prices = {
            "date": all_price_data.get("date", ""),
            "cities": all_price_data.get("states", {}).get(state_key, {}).get("cities", {}),
        }
        out_path = f"{output_dir}/{state_key}_{today_str}.jpg"
        try:
            generate_thumbnail(language, state_key, state_prices, out_path)
            results[state_key] = out_path
        except Exception as e:
            logger.error(f"Thumbnail failed for {state_key}: {e}")
            results[state_key] = None
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_data = {
        "date": "26 Jun 2026",
        "cities": {
            "Hyderabad":      {"22k_per_gram": 6750, "24k_per_gram": 7180, "22k_per_10g": 67500, "24k_per_10g": 71800},
            "Vijayawada":     {"22k_per_gram": 6745, "24k_per_gram": 7175, "22k_per_10g": 67450, "24k_per_10g": 71750},
            "Visakhapatnam":  {"22k_per_gram": 6748, "24k_per_gram": 7178, "22k_per_10g": 67480, "24k_per_10g": 71780},
        },
    }
    path = generate_thumbnail("telugu", "andhra_pradesh", test_data, "/tmp/test_thumb.jpg")
    print(f"Saved: {path}")
