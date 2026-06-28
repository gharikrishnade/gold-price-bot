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
from pathlib import Path
from datetime import date

logger = logging.getLogger(__name__)

# ── Language data ─────────────────────────────────────────────────────────────
LANG_STRINGS = {
    "telugu":    {"title": "నేటి బంగారం ధర",        "native": "తెలుగు",   "c22": "22 కెరట్",  "c24": "24 కెరట్",  "font": "Kohinoor Telugu, Noto Sans Telugu"},
    "tamil":     {"title": "இன்றைய தங்கம் விலை",   "native": "தமிழ்",    "c22": "22 கேரட்",  "c24": "24 கேரட்",  "font": "Kohinoor Tamil, Noto Sans Tamil"},
    "kannada":   {"title": "ಇಂದಿನ ಚಿನ್ನದ ಬೆಲೆ",    "native": "ಕನ್ನಡ",   "c22": "22 ಕ್ಯಾರಟ್","c24": "24 ಕ್ಯಾರಟ್","font": "Kannada MN, Noto Sans Kannada"},
    "malayalam": {"title": "ഇന്നത്തെ സ്വർണ്ണ വില", "native": "മലയാളം",  "c22": "22 കാരറ്റ്","c24": "24 കാരറ്റ്","font": "Malayalam MN, Noto Sans Malayalam"},
    "hindi":     {"title": "आज का सोने का भाव",      "native": "हिंदी",    "c22": "22 कैरेट",  "c24": "24 कैरेट",  "font": "Kohinoor Devanagari, Noto Sans Devanagari"},
    "marathi":   {"title": "आजचा सोन्याचा भाव",     "native": "मराठी",   "c22": "22 कॅरेट",  "c24": "24 कॅरेट",  "font": "Kohinoor Devanagari, Noto Sans Devanagari"},
    "bengali":   {"title": "আজকের সোনার দাম",        "native": "বাংলা",   "c22": "22 ক্যারেট","c24": "24 ক্যারেট","font": "Bangla MN, Noto Sans Bengali"},
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

    regional_font = s["font"]

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
    background: #160c02;
  }}

  .wrapper {{
    display: flex;
    width: {width}px;
    height: {height}px;
  }}

  /* ── LEFT COLUMN ── */
  .left {{
    width: {px(265)};
    height: {height}px;
    background: #160c02;
    display: flex;
    flex-direction: column;
    align-items: center;
    flex-shrink: 0;
    border-right: {px(3)} solid #B8860B;
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
    color: #FFD700;
    letter-spacing: {px(1)};
    text-align: center;
  }}
  .lang-native {{
    font-family: '{regional_font}', sans-serif;
    font-size: {px(17)};
    color: #A07808;
    text-align: center;
  }}

  .date-box {{
    width: 100%;
    background: #2A1802;
    text-align: center;
    padding: {px(14)} {px(8)} {px(18)};
    border-top: {px(2)} solid #8B6400;
  }}
  .date-label {{
    font-size: {px(12)};
    font-weight: 700;
    color: #8B6400;
    letter-spacing: {px(2)};
    margin-bottom: {px(4)};
  }}
  .date-value {{
    font-size: {px(20)};
    font-weight: 900;
    color: #FFD700;
  }}

  /* ── RIGHT AREA ── */
  .right {{
    flex: 1;
    display: flex;
    flex-direction: column;
    background: linear-gradient(160deg, #DAA520 0%, #B8850A 100%);
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
  }}
  .main-title {{
    font-family: '{regional_font}', sans-serif;
    font-size: {px(70)};
    font-weight: 700;
    color: #1A0C00;
    line-height: 1.1;
    margin-bottom: {px(4)};
  }}
  .sub-title {{
    font-size: {px(19)};
    font-weight: 600;
    color: #3A1E00;
  }}

  .divider {{
    height: {px(2)};
    background: linear-gradient(to right, transparent, #8B6400 30%, #8B6400 70%, transparent);
    margin-bottom: {px(12)};
  }}

  /* ── CARDS ── */
  .cards {{
    display: flex;
    gap: {px(18)};
    flex: 1;
  }}

  .card {{
    flex: 1;
    border-radius: {px(14)};
    display: flex;
    flex-direction: column;
    align-items: center;
    overflow: hidden;
    padding-bottom: {px(18)};
  }}
  .card-22 {{ background: #1C1204; }}
  .card-24 {{ background: #380404; }}

  .card-bar {{
    width: 100%; height: {px(8)};
    flex-shrink: 0;
    margin-bottom: {px(14)};
  }}
  .card-22 .card-bar {{ background: #DAA520; }}
  .card-24 .card-bar {{ background: #C01818; }}

  .carat-lbl {{
    font-size: {px(24)};
    font-weight: 900;
    letter-spacing: {px(2)};
    margin-bottom: {px(8)};
  }}
  .card-22 .carat-lbl {{ color: #DAA520; }}
  .card-24 .carat-lbl {{ color: #FF8888; }}

  .price-num {{
    font-size: {px(96)};
    font-weight: 900;
    color: #FFFFFF;
    letter-spacing: -{px(2)};
    line-height: 1;
    margin-bottom: {px(4)};
  }}

  .per-gram {{
    font-size: {px(22)};
    font-weight: 700;
    margin-bottom: {px(12)};
  }}
  .card-22 .per-gram {{ color: #DAA520; }}
  .card-24 .per-gram {{ color: #FF9090; }}

  .card-sep {{
    width: calc(100% - {px(40)});
    height: 1px;
    margin-bottom: {px(12)};
  }}
  .card-22 .card-sep {{ background: rgba(180,140,0,0.35); }}
  .card-24 .card-sep {{ background: rgba(180,60,60,0.35); }}

  .price-10g {{
    font-size: {px(22)};
    font-weight: 600;
    margin-bottom: {px(6)};
  }}
  .card-22 .price-10g {{ color: #907040; }}
  .card-24 .price-10g {{ color: #906060; }}

  .grade-lbl {{
    font-family: '{regional_font}', sans-serif;
    font-size: {px(17)};
  }}
  .card-22 .grade-lbl {{ color: #6A5030; }}
  .card-24 .grade-lbl {{ color: #6A3030; }}

  /* ── BOTTOM BAR ── */
  .bottom-bar {{
    background: #160c02;
    height: {px(78)};
    display: flex;
    align-items: center;
    padding: 0 {px(16)} 0 {px(20)};
    border-top: {px(2)} solid #8B6400;
    flex-shrink: 0;
    gap: {px(12)};
  }}
  .cities {{
    font-family: '{regional_font}', sans-serif;
    font-size: {px(22)};
    color: #DAA520;
    flex: 1;
    text-align: center;
  }}
  .sub-btn {{
    background: #C01010;
    color: #fff;
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
    img = Image.new("RGB", (width, height), (22,12,2))
    draw = ImageDraw.Draw(img)
    # gold bg
    for y in range(height-bh):
        t = y/max(1,height-bh)
        draw.line([(lw,y),(width,y)], fill=(int(218-20*t),int(165-35*t),int(32+10*t)))
    draw.rectangle([(0,0),(lw,height)], fill=(22,12,2))
    draw.rectangle([(lw-3,0),(lw,height-bh)], fill=(184,134,11))
    # title
    cx = lw+(width-lw)//2
    draw.text((cx,int(62*sc)), s["title"], font=fnt(reg,int(70*sc)), fill=(26,12,0), anchor="mm")
    subtitle = "Today's Gold Rate — "+STATE_DISPLAY.get(state_key, state_key.replace("_"," ").title())
    draw.text((cx,int(108*sc)), subtitle, font=fnt(latin,int(19*sc)), fill=(58,30,0), anchor="mm")
    draw.line([(lw+int(18*sc),int(124*sc)),(width-int(18*sc),int(124*sc))], fill=(139,100,0), width=2)
    # cards
    gap=int(18*sc); cy=int(134*sc); ch=int(500*sc)
    cw=(width-lw-gap*3)//2; x22=lw+gap; x24=x22+cw+gap
    for x,bg,acc,lbl,p,p10,cs in [
        (x22,(28,18,4),(218,165,32),"22 CARAT",p22g,p22_10,s["c22"]),
        (x24,(56,4,4),(192,24,24),"24 CARAT",p24g,p24_10,s["c24"]),
    ]:
        draw.rounded_rectangle([(x,cy),(x+cw,cy+ch)], radius=int(14*sc), fill=bg)
        draw.rounded_rectangle([(x,cy),(x+cw,cy+int(8*sc))], radius=int(5*sc), fill=acc)
        m = x+cw//2
        draw.text((m,cy+int(38*sc)), lbl, font=fnt(latin,int(24*sc)), fill=acc, anchor="mm")
        draw.text((m,cy+int(175*sc)), f"{p:,}", font=fnt(latin,int(96*sc)), fill=(255,255,255), anchor="mm")
        draw.text((m,cy+int(245*sc)), "₹ per gram", font=fnt(latin,int(22*sc)), fill=acc, anchor="mm")
        draw.line([(x+int(28*sc),cy+int(272*sc)),(x+cw-int(28*sc),cy+int(272*sc))], fill=(100,80,0), width=1)
        draw.text((m,cy+int(315*sc)), f"₹{p10:,} / 10 grams", font=fnt(latin,int(22*sc)), fill=(130,110,70), anchor="mm")
        draw.text((m,cy+int(360*sc)), f"{cs} · Jewellery" if "22" in lbl else f"{cs} · Investment", font=fnt(reg,int(17*sc)), fill=(100,80,50), anchor="mm")
    # bottom
    by=height-bh
    draw.rectangle([(lw,by),(width,height)], fill=(22,12,2))
    draw.line([(lw,by),(width,by)], fill=(139,100,0), width=2)
    draw.text(((lw+width-int(160*sc))//2,by+bh//2), "  ·  ".join(city_names), font=fnt(reg,int(22*sc)), fill=(218,165,32), anchor="mm")
    bw,bhh=int(150*sc),int(38*sc)
    bx=width-bw-int(14*sc); bby=by+(bh-bhh)//2
    draw.rounded_rectangle([(bx,bby),(bx+bw,bby+bhh)], radius=int(7*sc), fill=(192,16,16))
    draw.text((bx+bw//2,bby+bhh//2), "▶  SUBSCRIBE", font=fnt(latin,int(16*sc)), fill=(255,255,255), anchor="mm")
    # date box
    dbh=int(86*sc); dby=height-bh-dbh
    draw.rectangle([(0,dby),(lw-3,height-bh)], fill=(42,24,4))
    draw.line([(0,dby),(lw-3,dby)], fill=(139,100,0), width=2)
    draw.text((lw//2,dby+int(18*sc)), "DATE", font=fnt(latin,int(12*sc)), fill=(139,100,0), anchor="mm")
    draw.text((lw//2,dby+int(52*sc)), date_str, font=fnt(latin,int(20*sc)), fill=(255,215,0), anchor="mm")
    # coin
    coin_r=int(72*sc); ccx=lw//2; ccy=int(248*sc)
    draw.ellipse([(ccx-coin_r,ccy-coin_r),(ccx+coin_r,ccy+coin_r)], fill=(160,110,5))
    draw.ellipse([(ccx-int(coin_r*.88),ccy-int(coin_r*.88)),(ccx+int(coin_r*.88),ccy+int(coin_r*.88))], fill=(218,165,32))
    draw.ellipse([(ccx-int(coin_r*.70),ccy-int(coin_r*.70)),(ccx+int(coin_r*.70),ccy+int(coin_r*.70))], fill=(140,95,0))
    draw.text((ccx,ccy+int(coin_r*.06)), "₹", font=fnt(latin,int(coin_r*.75)), fill=(255,235,100), anchor="mm")
    draw.text((lw//2,ccy+coin_r+int(20*sc)), "GOLD UPDATES", font=fnt(latin,int(14*sc)), fill=(255,215,0), anchor="mm")
    draw.text((lw//2,ccy+coin_r+int(40*sc)), s["native"], font=fnt(reg,int(16*sc)), fill=(160,120,10), anchor="mm")

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
