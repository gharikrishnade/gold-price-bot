"""
review_page.py - Generate a local HTML review page for run artifacts.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def write_review_page(
    all_results: dict[str, dict[str, Any]],
    *,
    output_path: str | Path,
    summary_path: str,
    review_summary_path: str,
) -> str:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        _build_review_html(
            all_results,
            output_dir=output.parent,
            summary_path=summary_path,
            review_summary_path=review_summary_path,
        ),
        encoding="utf-8",
    )
    return str(output)


def _build_review_html(
    all_results: dict[str, dict[str, Any]],
    *,
    output_dir: Path,
    summary_path: str,
    review_summary_path: str,
) -> str:
    completed = [
        state_key for state_key, result in all_results.items()
        if result.get("upload_status") in {"success", "skipped"} and not result.get("error")
    ]
    failed = [state_key for state_key, result in all_results.items() if result.get("error")]
    run_date = next(iter(all_results.values()), {}).get("run_date", "")

    state_sections = "\n".join(
        _state_section(state_key, result, output_dir)
        for state_key, result in all_results.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gold Price Bot Review {escape(str(run_date))}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f4ee;
      --panel: #ffffff;
      --ink: #201a12;
      --muted: #6d6256;
      --line: #ded5c8;
      --ok: #17633a;
      --warn: #8a5200;
      --bad: #a12828;
      --gold: #b8860b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 22px;
    }}
    h1 {{ margin: 0; font-size: 30px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 22px; letter-spacing: 0; }}
    .muted {{ color: var(--muted); }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 22px;
    }}
    .metric, .state {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric strong {{ display: block; font-size: 28px; }}
    .states {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .state-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .badge {{
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .badge.ok {{ color: var(--ok); background: #e6f4eb; }}
    .badge.warn {{ color: var(--warn); background: #fff1d8; }}
    .badge.bad {{ color: var(--bad); background: #fbe6e6; }}
    dl {{
      display: grid;
      grid-template-columns: 130px 1fr;
      gap: 8px 12px;
      margin: 0 0 14px;
      font-size: 14px;
    }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    a {{ color: #795400; text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    .thumb {{
      width: 100%;
      aspect-ratio: 16 / 9;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #eee;
      margin-bottom: 12px;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .links a {{
      border: 1px solid var(--line);
      background: #fbfaf7;
      border-radius: 6px;
      padding: 7px 10px;
      text-decoration: none;
      font-size: 14px;
    }}
    .error {{
      color: var(--bad);
      background: #fff5f5;
      border: 1px solid #f0cccc;
      border-radius: 6px;
      padding: 10px;
      margin-top: 10px;
      overflow-wrap: anywhere;
    }}
    details {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      margin-top: 12px;
      background: #fffdf9;
    }}
    summary {{
      cursor: pointer;
      font-weight: 700;
    }}
    .metadata {{
      margin-top: 10px;
      margin-bottom: 0;
    }}
    .description {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      max-height: 220px;
      overflow: auto;
      border-top: 1px solid var(--line);
      padding-top: 8px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    footer {{
      margin-top: 24px;
      border-top: 1px solid var(--line);
      padding-top: 18px;
      font-size: 14px;
    }}
    @media (max-width: 760px) {{
      header {{ display: block; }}
      .summary {{ grid-template-columns: 1fr; }}
      dl {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Gold Price Bot Review</h1>
        <div class="muted">{escape(str(run_date))}</div>
      </div>
      <div class="muted">{len(all_results)} state run(s)</div>
    </header>

    <section class="summary" aria-label="Run summary">
      <div class="metric"><span class="muted">Completed</span><strong>{len(completed)}</strong></div>
      <div class="metric"><span class="muted">Failed</span><strong>{len(failed)}</strong></div>
      <div class="metric"><span class="muted">Artifacts</span><strong>{_artifact_count(all_results)}</strong></div>
    </section>

    <section class="states" aria-label="State outputs">
      {state_sections}
    </section>

    <footer>
      <div>Log summary: {_path_link(summary_path, output_dir)}</div>
      <div>Review summary: {_path_link(review_summary_path, output_dir)}</div>
    </footer>
  </main>
</body>
</html>
"""


def _state_section(state_key: str, result: dict[str, Any], output_dir: Path) -> str:
    status = _state_status(result)
    badge_class = {"completed": "ok", "skipped": "warn", "failed": "bad"}.get(status, "warn")
    thumb = _thumbnail_html(result.get("thumbnail_path"), output_dir)
    links = _artifact_links(result, output_dir)
    metadata = _metadata_html(result.get("youtube_metadata"))
    error = result.get("error")
    error_html = f'<div class="error">{escape(str(error))}</div>' if error else ""

    return f"""<article class="state">
  <div class="state-head">
    <div>
      <h2>{escape(state_key.replace("_", " ").title())}</h2>
      <div class="muted">{escape(str(result.get("language", "")))} · {escape(str(result.get("region_name", "")))}</div>
    </div>
    <span class="badge {badge_class}">{escape(status)}</span>
  </div>
  {thumb}
  <dl>
    <dt>Scrape</dt><dd>{escape(str(result.get("scrape_status", "unknown")))}</dd>
    <dt>Validation</dt><dd>{escape(str(result.get("price_validation_status", "unknown")))}</dd>
    <dt>Script</dt><dd>{escape(str(result.get("script_generation_status", "unknown")))}</dd>
    <dt>Audio</dt><dd>{escape(str(result.get("audio_status", "unknown")))}{_optional_suffix(result.get("audio_duration_seconds"), "s")}</dd>
    <dt>Video</dt><dd>{escape(str(result.get("video_status", "unknown")))}{_optional_suffix(result.get("video_size_mb"), " MB")}</dd>
    <dt>Upload</dt><dd>{escape(str(result.get("upload_status", "unknown")))}{_skip_reason(result)}</dd>
    <dt>Approval</dt><dd>{_approval_status(result, output_dir)}</dd>
    <dt>Privacy</dt><dd>{escape(str(result.get("privacy_status", "")))}</dd>
  </dl>
  {metadata}
  {links}
  {error_html}
</article>"""


def _state_status(result: dict[str, Any]) -> str:
    if result.get("error"):
        return "failed"
    if result.get("upload_status") == "skipped":
        return "skipped"
    if result.get("upload_status") == "success":
        return "completed"
    return str(result.get("upload_status", "unknown"))


def _thumbnail_html(path: str | None, output_dir: Path) -> str:
    if not path or not Path(path).exists():
        return ""
    rel = escape(_relative_path(path, output_dir))
    return f'<img class="thumb" src="{rel}" alt="Generated thumbnail">'


def _artifact_links(result: dict[str, Any], output_dir: Path) -> str:
    candidates = [
        ("Script", result.get("script_path")),
        ("Thumbnail", result.get("thumbnail_path")),
        ("Audio", result.get("audio_path")),
        ("Video", result.get("video_path")),
        ("YouTube", result.get("youtube_url")),
    ]
    links = []
    for label, path in candidates:
        if not path:
            continue
        if str(path).startswith("http"):
            href = escape(str(path))
        elif Path(path).exists():
            href = escape(_relative_path(path, output_dir))
        else:
            continue
        links.append(f'<a href="{href}">{escape(label)}</a>')
    return f'<div class="links">{"".join(links)}</div>' if links else ""


def _metadata_html(metadata: dict[str, Any] | None) -> str:
    if not metadata:
        return ""
    tags = ", ".join(str(tag) for tag in metadata.get("tags", []))
    description = metadata.get("description", "")
    return f"""<details>
  <summary>YouTube metadata</summary>
  <dl class="metadata">
    <dt>Title</dt><dd>{escape(str(metadata.get("title", "")))}</dd>
    <dt>Privacy</dt><dd>{escape(str(metadata.get("privacy_status", "")))}</dd>
    <dt>Language</dt><dd>{escape(str(metadata.get("default_language", "")))}</dd>
    <dt>Tags</dt><dd>{escape(tags)}</dd>
  </dl>
  <div class="description">{escape(str(description))}</div>
</details>"""


def _path_link(path: str, output_dir: Path) -> str:
    if Path(path).exists():
        href = escape(_relative_path(path, output_dir))
        return f'<a href="{href}">{escape(path)}</a>'
    return escape(path)


def _relative_path(path: str, output_dir: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(output_dir.resolve()))
    except ValueError:
        return str(Path(path).resolve())


def _optional_suffix(value: Any, suffix: str) -> str:
    if value is None or value == "":
        return ""
    return f" ({escape(str(value))}{escape(suffix)})"


def _skip_reason(result: dict[str, Any]) -> str:
    reason = result.get("upload_skip_reason")
    return f" ({escape(str(reason))})" if reason else ""


def _approval_status(result: dict[str, Any], output_dir: Path) -> str:
    if not result.get("require_upload_approval"):
        return "Not required"
    marker_path = result.get("approval_marker_path")
    instructions_path = result.get("approval_instructions_path")
    if marker_path and Path(marker_path).exists():
        return "Approved"
    if instructions_path and Path(instructions_path).exists():
        return f'Required ({_plain_path_link(instructions_path, output_dir)})'
    if marker_path:
        return f"Required; marker: {escape(str(marker_path))}"
    return "Required"


def _plain_path_link(path: str, output_dir: Path) -> str:
    href = escape(_relative_path(path, output_dir))
    return f'<a href="{href}">{escape(str(Path(path).name))}</a>'


def _artifact_count(all_results: dict[str, dict[str, Any]]) -> int:
    keys = ("script_path", "thumbnail_path", "audio_path", "video_path")
    return sum(1 for result in all_results.values() for key in keys if result.get(key))
