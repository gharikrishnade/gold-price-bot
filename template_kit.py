"""
template_kit.py — Shared visual building blocks for content-show templates.

A show renders its on-screen card (landscape 16:9 and portrait 9:16) by describing
WHAT to show (`CardContent` + `StatCard`) and WHICH look (`Brand`), then calling
`render_card()`. The heavy lifting — layout, fonts, Chromium rendering — is shared,
so a new show composes a polished card without copying CSS. A `Brand` lets shows look
visually distinct while sharing the same layout primitives.

Tracker: TMPL-001 (component library), TMPL-002 (per-show branding).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Branding (TMPL-002) ───────────────────────────────────────────────────────
@dataclass
class Brand:
    """A show's visual identity: palette, typography, and logo glyph."""
    key: str
    wordmark: str                      # small label by the logo, e.g. "GOLD UPDATES"
    emblem: str = "₹"                  # glyph inside the logo bubble
    bg: str = "#0b1020"
    panel: str = "#1f2937"
    panel_border: str = "#334155"
    accent: str = "#f6c453"            # titles, logo, primary accent
    accent_2: str = "#22c55e"          # first stat-card accent
    accent_3: str = "#f59e0b"          # second stat-card accent
    text: str = "#ffffff"
    text_muted: str = "#94a3b8"
    title_font: str = "Georgia, 'Times New Roman', serif"  # latin fallback; Indic via regional_font
    body_font: str = "'Helvetica Neue', Arial, sans-serif"

    def css_vars(self) -> str:
        return (
            ":root{"
            f"--bg:{self.bg};--panel:{self.panel};--panel-border:{self.panel_border};"
            f"--accent:{self.accent};--accent-2:{self.accent_2};--accent-3:{self.accent_3};"
            f"--text:{self.text};--text-muted:{self.text_muted};"
            f"--title-font:{self.title_font};--body-font:{self.body_font};"
            "}"
        )


# Gold's current look captured as a brand (kept here so new shows can copy/contrast).
GOLD_BRAND = Brand(
    key="gold", wordmark="GOLD UPDATES", emblem="₹",
    bg="#0b1020", panel="#1f2937", panel_border="#334155",
    accent="#f6c453", accent_2="#22c55e", accent_3="#f59e0b",
)


# ── Content model ─────────────────────────────────────────────────────────────
@dataclass
class StatCard:
    label: str                 # e.g. "22 CARAT"
    value: str                 # big number/text, e.g. "13,370"
    unit: str = ""             # e.g. "₹ per gram"
    footer: str = ""           # e.g. "₹133,700 / 10 grams"
    accent: str | None = None  # override; defaults to brand accent_2 / accent_3 by position


@dataclass
class CardContent:
    title: str                          # headline (may be regional script)
    subtitle: str = ""                  # latin sub-line
    date_str: str = ""                  # shown as a pill in the header
    stats: list[StatCard] = field(default_factory=list)
    footer_text: str = ""               # e.g. city list (may be regional script)
    cta: str = "SUBSCRIBE"
    title_font_css: str | None = None   # regional font stack for the title, if any
    footer_font_css: str | None = None  # regional font stack for the footer, if any


# ── Render primitive (shared) ─────────────────────────────────────────────────
def render_html_to_image(html: str, output_path: str, width: int, height: int) -> str:
    """Render an HTML string to a JPEG at exact width×height via headless Chromium."""
    from playwright.sync_api import sync_playwright

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(500)  # let webfonts settle
        page.screenshot(
            path=output_path, type="jpeg", quality=95,
            clip={"x": 0, "y": 0, "width": width, "height": height},
        )
        browser.close()
    logger.info(f"Template rendered ({width}×{height}): {output_path}")
    return output_path


# ── Font helpers (shared) ─────────────────────────────────────────────────────
def css_font_stack(font_stack: str) -> str:
    return ", ".join(f"'{f.strip()}'" for f in font_stack.split(",") if f.strip())


def fit_font_size(text: str, base_size: int, min_size: int, soft_limit: int) -> int:
    if len(text) <= soft_limit:
        return base_size
    return max(min_size, base_size - (len(text) - soft_limit) * 2)


# ── Composable card (TMPL-001) ────────────────────────────────────────────────
def render_card(brand: Brand, content: CardContent, output_path: str, *, fmt: str = "landscape",
                width: int | None = None, height: int | None = None) -> str:
    """Compose a full branded card and render it. fmt: "landscape" (16:9) or "portrait" (9:16)."""
    if fmt == "portrait":
        w, h, base = width or 1080, height or 1920, 1080
    elif fmt == "landscape":
        w, h, base = width or 1280, height or 720, 1280
    else:
        raise ValueError(f"Unknown fmt '{fmt}'; use 'landscape' or 'portrait'")
    html = build_card_html(brand, content, fmt=fmt, width=w, height=h, base=base)
    return render_html_to_image(html, output_path, w, h)


def build_card_html(brand: Brand, content: CardContent, *, fmt: str, width: int, height: int, base: int) -> str:
    """Return the HTML for a branded card (no rendering). Useful for previews/tests."""
    scale = width / base
    def px(v): return round(v * scale)

    portrait = fmt == "portrait"
    title_font = content.title_font_css or css_font_stack(brand.title_font)
    footer_font = content.footer_font_css or css_font_stack(brand.body_font)

    # Card width (to auto-size big values so words like "Confident" don't overflow).
    pad = px(64 if portrait else 56)
    gap_px = px(28)
    inner_pad = px(36)
    ncards = max(len(content.stats), 1)
    if portrait:
        card_w = width - 2 * pad
    else:
        card_w = (width - 2 * pad - (ncards - 1) * gap_px) / ncards
    card_inner = max(card_w - 2 * inner_pad, px(80))

    def _value_px(value: str) -> int:
        # ~0.62 avg glyph-width ratio for the bold sans; cap at the design size.
        fit = int(card_inner / (0.62 * max(len(value), 1)))
        return max(px(34), min(px(120), fit))

    accents = [brand.accent_2, brand.accent_3]
    cards_html = ""
    for i, st in enumerate(content.stats):
        accent = st.accent or accents[i % len(accents)]
        cards_html += f"""
      <div class="card" style="--c:{accent}">
        <div class="card-bar"></div>
        <div class="card-body">
          <div class="card-label">{escape(st.label)}</div>
          <div class="card-value" style="font-size:{_value_px(st.value)}px">{escape(st.value)}</div>
          {f'<div class="card-unit">{escape(st.unit)}</div>' if st.unit else ''}
          {f'<div class="card-foot">{escape(st.footer)}</div>' if st.footer else ''}
        </div>
      </div>"""

    date_pill = f'<div class="date-pill">{escape(content.date_str)}</div>' if content.date_str else ""
    subtitle = f'<div class="subtitle">{escape(content.subtitle)}</div>' if content.subtitle else ""
    footer_text = f'<div class="footer-text">{escape(content.footer_text)}</div>' if content.footer_text else ""

    # Layout differences between formats.
    stats_dir = "column" if portrait else "row"
    title_size = px(108 if portrait else 84)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  {brand.css_vars()}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{width}px; height:{height}px; overflow:hidden; }}
  body {{ background:var(--bg); color:var(--text); font-family:var(--body-font);
          display:flex; flex-direction:column; padding:{pad}px; }}
  .head {{ display:flex; flex-direction:column; align-items:center; text-align:center; gap:{px(8)}px; }}
  .logo {{ display:flex; align-items:center; gap:{px(14)}px; margin-bottom:{px(6)}px; }}
  .logo .bubble {{ width:{px(64)}px; height:{px(64)}px; border-radius:50%;
                   background:var(--accent); color:var(--bg); font-weight:800;
                   font-size:{px(34)}px; display:flex; align-items:center; justify-content:center; }}
  .logo .mark {{ font-size:{px(24)}px; font-weight:800; letter-spacing:{px(2)}px; color:var(--accent); }}
  .title {{ font-family:{title_font}; font-weight:800; color:var(--accent);
            font-size:{title_size}px; line-height:1.05; }}
  .subtitle {{ font-size:{px(30)}px; font-weight:600; color:var(--text-muted); }}
  .date-pill {{ margin-top:{px(8)}px; align-self:center; background:var(--panel);
                border:{px(2)}px solid var(--panel-border); border-radius:{px(40)}px;
                padding:{px(10)}px {px(24)}px; font-size:{px(26)}px; font-weight:800; color:var(--accent); }}
  .stats {{ flex:1; display:flex; flex-direction:{stats_dir}; gap:{px(28)}px;
            align-items:stretch; justify-content:center; margin:{px(36)}px 0; }}
  .card {{ flex:1; background:var(--panel); border:{px(2)}px solid var(--panel-border);
           border-radius:{px(20)}px; overflow:hidden; display:flex; flex-direction:column;
           box-shadow:0 {px(18)}px {px(30)}px rgba(0,0,0,.35); }}
  .card-bar {{ height:{px(8)}px; background:var(--c); }}
  .card-body {{ padding:{px(36)}px; display:flex; flex-direction:column; align-items:center;
                justify-content:center; gap:{px(8)}px; flex:1; text-align:center; }}
  .card-label {{ font-size:{px(30)}px; font-weight:800; letter-spacing:{px(2)}px; color:var(--c); }}
  .card-value {{ font-size:{px(120)}px; font-weight:800; line-height:1; color:var(--text); }}
  .card-unit {{ font-size:{px(28)}px; font-weight:700; color:var(--c); }}
  .card-foot {{ margin-top:{px(6)}px; font-size:{px(26)}px; color:var(--text-muted); }}
  .foot {{ display:flex; align-items:center; justify-content:space-between; gap:{px(16)}px; }}
  .footer-text {{ font-family:{footer_font}; font-size:{px(28)}px; font-weight:700; color:var(--accent); }}
  .cta {{ background:var(--accent); color:var(--bg); font-weight:800; font-size:{px(24)}px;
          border-radius:{px(12)}px; padding:{px(12)}px {px(22)}px; white-space:nowrap; }}
</style></head><body>
  <div class="head">
    <div class="logo"><div class="bubble">{escape(brand.emblem)}</div><div class="mark">{escape(brand.wordmark)}</div></div>
    <div class="title">{content.title}</div>
    {subtitle}
    {date_pill}
  </div>
  <div class="stats">{cards_html}
  </div>
  <div class="foot">
    {footer_text}
    <div class="cta">▶ {escape(content.cta)}</div>
  </div>
</body></html>"""
