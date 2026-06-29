# Multi-Content Video Platform Requirements

## Purpose

This document captures the requirements to evolve the current single-purpose **Gold Price YouTube Bot**
into a general-purpose **automated video content platform** that can produce many kinds of daily videos
(gold prices, stock-market updates, daily horoscope, and future shows) from one shared engine.

It is intended to be used as a **living tracker** for this expansion. Update the **Status** of each
requirement as work progresses, and keep the tracker table in sync.

Related: see [`application_improvement_requirements.md`](application_improvement_requirements.md) for the
original gold-bot hardening requirements (most of which are now implemented and form the reusable engine).

## Vision Summary

The existing pipeline (`script → voice → template → video → publish`) is already domain-agnostic. Only a
thin slice is gold-specific (data fetch, validation, history, prompt facts, card layout, metadata). The
expansion draws a clean seam between the two:

- A **Core Pipeline Engine** + **Shared Services** that every show reuses.
- Pluggable **Content Modules** (one per show) that supply only the domain-specific parts.
- A **Jobs/Shows config** layer that maps shows × channels × languages × schedule to modules.

The first content module (Gold) is live today. Stocks and Horoscope are the first two new modules and
are deliberately chosen to stress-test the abstraction (API data + charts; and no-data + stateless).

## Status Legend

- `TODO` — not started.
- `WIP` — in progress.
- `DONE` — implemented and verified.
- `BLOCKED` — waiting on a decision or dependency (note the blocker).
- `N/A` — descoped.

## Priority Levels

- **P0**: Required to ship the multi-content platform at all.
- **P1**: Strongly recommended before onboarding the 2nd/3rd show at scale.
- **P2**: Useful enhancements once multiple shows are live.

## Tracker Overview

| ID | Requirement | Phase | Priority | Status | Owner |
|----|-------------|-------|----------|--------|-------|
| PLAT-001 | ContentModule interface (the seam) | 1 | P0 | DONE | |
| PLAT-002 | Extract Gold into a module | 1 | P0 | DONE | |
| PLAT-003 | Engine delegates to module (no behavior change) | 1 | P0 | DONE | |
| PLAT-004 | Shared script engine (tone/language as platform asset) | 2 | P0 | DONE | |
| PLAT-005 | Jobs/Shows config layer | 3 | P0 | DONE | |
| PLAT-006 | Scheduler / orchestrator for due jobs | 3 | P1 | DONE | |
| PLAT-007 | Optional history per module (`needs_history`) | 1 | P0 | DONE | |
| PLAT-008 | Generalized dedupe & run keys | 3 | P1 | DONE | |
| TMPL-001 | Template component library | 4 | P1 | TODO | |
| TMPL-002 | Per-show branding system | 4 | P1 | TODO | |
| MOD-GOLD-001 | Gold module parity after refactor | 1 | P0 | DONE | |
| MOD-STOCK-001 | Stocks module (API data, market calendar) | 5 | P1 | TODO | |
| MOD-STOCK-002 | Stocks charts & stat cards | 5 | P1 | TODO | |
| MOD-STOCK-003 | Financial-advice disclaimer | 5 | P0 | TODO | |
| MOD-HORO-001 | Horoscope module (12 signs, stateless) | 6 | P1 | TODO | |
| MOD-HORO-002 | Horoscope content-safety framing | 6 | P0 | TODO | |
| OPS-001 | Cost & rate-limit guardrails | 7 | P1 | TODO | |
| OPS-002 | Observability + failure alerting | 7 | P1 | TODO | |
| OPS-003 | Multi-channel secrets management | 7 | P1 | TODO | |
| OPS-004 | YouTube analytics feedback loop | 7 | P2 | TODO | |
| OPS-005 | Golden-output test harness | 7 | P1 | TODO | |
| PROJ-001 | Rename project to reflect new scope | 4 | P2 | TODO | |

---

## Platform / Engine Requirements

### PLAT-001: ContentModule Interface

**Phase:** 1 · **Priority:** P0 · **Status:** DONE

Define a single interface (Python `Protocol`/ABC) that every show implements. The engine must call only
these methods and must never reference a specific domain (gold, stocks, etc.).

Requirements:

- Define `key`, `display_name`, and `needs_history` attributes.
- Define methods: `fetch()`, `validate()`, `build_context()`, `script_brief()`, `render_template(fmt)`,
  `youtube_metadata()`.
- `script_brief()` returns structured facts + a short domain framing + any disclaimers (not raw prompt text).
- `render_template(fmt)` returns HTML for both `landscape` (16:9) and `portrait` (9:16).
- Provide a `REGISTRY` mapping module keys to implementations.

Acceptance criteria:

- The engine can run end-to-end calling only interface methods.
- Adding a new module requires no changes to engine code, only a new registry entry.

### PLAT-002: Extract Gold Into a Module

**Phase:** 1 · **Priority:** P0 · **Status:** DONE

Move all gold-specific logic (`scraper.get_state_prices`, `price_validator`, gold history,
gold prompt facts, gold card template, per-state YouTube metadata) into `modules/gold/` behind PLAT-001.

Acceptance criteria:

- `modules/gold/` is the only place that knows about GoodReturns, "state", cities, or karat.
- See MOD-GOLD-001 for behavior parity.

### PLAT-003: Engine Delegates to Module

**Phase:** 1 · **Priority:** P0 · **Status:** DONE

Refactor `main.py` so the pipeline (fetch → validate → context → script → voice → template → video →
publish → review) delegates each domain-specific step to the selected module. Keep all generic
orchestration (retries, run dirs, approval gate, dedupe, summary, notifications) in the engine.

Acceptance criteria:

- No domain conditionals (`if state == ...`) remain in engine code.
- Gold runs are byte-for-byte equivalent in behavior to before the refactor (strangler-fig: gold never breaks).

### PLAT-004: Shared Script Engine

**Phase:** 2 · **Priority:** P0 · **Status:** DONE — script_engine.py owns persona/tone/language/CTA + LANGUAGE_META; gold builds ScriptBriefs. Verified gold long+short parity end-to-end.

Promote the existing regional scripting rules (regional currency/units, no Latin letters, carat spelled
out, polite-conversational tone, plain everyday words, code-mixing transliterated into the native script,
mandatory CTA, max_tokens headroom + truncation guard) out of the gold code and into a shared
`script_engine` that consumes a `ScriptBrief`.

Requirements:

- `script_engine.generate(brief, language, length)` applies all shared tone/language/TTS rules.
- Supports a `short` variant (~30s) and a `long` variant.
- Modules supply only facts + domain framing + disclaimers; the engine supplies the voice.

Acceptance criteria:

- Stocks and Horoscope scripts inherit correct regional currency/units/CTA behavior without re-implementing rules.
- Changing a tone rule once updates all shows.

### PLAT-005: Jobs / Shows Config Layer

**Phase:** 3 · **Priority:** P0 · **Status:** DONE — jobs.yaml + jobs_config.py; CHANNEL_CONFIG derived from gold jobs; engine runs from jobs with --job/--module/--state filters and per-job formats

Replace `CHANNEL_CONFIG` (state→language) with a data-driven jobs config (YAML/JSON or DB) so new shows
can be added without code changes.

Requirements:

- Each job declares: `module`, `params`, `language`, `youtube_token`, `schedule`, `formats` (long/short), branding ref.
- A "channel" generalizes a state: gold-in-TamilNadu, NIFTY-in-Hindi, Aries-in-English.
- Config is validated on load with clear errors.

Acceptance criteria:

- Adding a new show is a config edit + (if new domain) a module, not an engine change.

### PLAT-006: Scheduler / Orchestrator

**Phase:** 3 · **Priority:** P1 · **Status:** DONE — `--due` runs jobs whose jobs.yaml `schedule` is within `--window-minutes` of now (single frequent cron); per-job failure isolation; `--list-jobs`

Run jobs by their declared schedule rather than a single daily cron for all states.

Requirements:

- Iterate jobs due now; run engine per job; isolate failures per job.
- Reuse existing notification + run-summary infrastructure.

Acceptance criteria:

- A stocks job at 16:00 and a horoscope job at 05:00 run independently on schedule.

### PLAT-007: Optional History Per Module

**Phase:** 1 · **Priority:** P0 · **Status:** DONE

Generalize history/state so some modules persist series (gold, stocks) and some are stateless (horoscope).

Requirements:

- `needs_history=False` modules skip storage/comparison entirely.
- History API is keyed generically by `(module, channel, date)`.

Acceptance criteria:

- A stateless module runs without any history tables or comparison language.

### PLAT-008: Generalized Dedupe & Run Keys

**Phase:** 3 · **Priority:** P1 · **Status:** DONE — upload-history keys are now <module>:<channel> (and __shorts), unique across modules

Generalize duplicate-upload protection and artifact keys beyond gold (already started with the
`<state>__shorts` key).

Acceptance criteria:

- Re-running any job for the same `(job, channel, date)` does not double-publish by default; `--force-upload` overrides.

---

## Template & Branding Requirements

### TMPL-001: Template Component Library

**Phase:** 4 · **Priority:** P1 · **Status:** TODO

Extract shared HTML/CSS components (header, card, portrait frame, footer, logo/coin slot, date pill,
animated trend/stat chart) so modules compose templates instead of copying CSS.

Acceptance criteria:

- A new module's template is built mostly from shared components.

### TMPL-002: Per-Show Branding System

**Phase:** 4 · **Priority:** P1 · **Status:** TODO

Allow each show to declare its own logo, color palette, fonts, intro/outro, and background music.

Acceptance criteria:

- Gold, Stocks, and Horoscope videos look visually distinct while sharing layout primitives.

---

## Content Module Requirements

### MOD-GOLD-001: Gold Module Parity

**Phase:** 1 · **Priority:** P0 · **Status:** DONE — verified via andhra_pradesh dry run end-to-end

After PLAT-002/003, the gold show must retain all current behavior.

Acceptance criteria:

- Regional script rules, city grouping, trend cards, long + short + shorts-only modes, and YouTube
  upload all behave as they do today.

### MOD-STOCK-001: Stocks Module — Data & Calendar

**Phase:** 5 · **Priority:** P1 · **Status:** TODO

First new module; validates the abstraction against API data instead of scraping.

Requirements:

- Fetch index/sector/ticker data from an API (e.g. NSE / Alpha Vantage / broker API), not a scrape.
- Respect market hours and a trading-holiday calendar; handle closed-market days.
- Channels = index/sector (e.g. NIFTY50, BANKNIFTY) × language.

Acceptance criteria:

- On a market holiday, the module produces a correct "market closed" script and does not invent moves.

### MOD-STOCK-002: Stocks Charts & Stat Cards

**Phase:** 5 · **Priority:** P1 · **Status:** TODO

Reuse the existing animated trend-chart rendering (`_trend_chart_svg`) as first-class stat cards for
stock movements.

Acceptance criteria:

- A stock video shows an animated index movement chart driven by real data.

### MOD-STOCK-003: Financial-Advice Disclaimer

**Phase:** 5 · **Priority:** P0 · **Status:** TODO

Every stock script and YouTube description must include a clear "not financial advice / for information
only" disclaimer.

Acceptance criteria:

- No stock video is produced without the disclaimer present in both script and description.

### MOD-HORO-001: Horoscope Module — 12 Signs, Stateless

**Phase:** 6 · **Priority:** P1 · **Status:** TODO

Second new module; validates the no-data / no-history / stateless path.

Requirements:

- Content is LLM-generated per zodiac sign; `needs_history=False`.
- 12 signs = 12 channels; natural fit for daily Shorts.
- Optional: planetary-position data source if accuracy is desired later.

Acceptance criteria:

- A daily horoscope Short is produced per sign with no external data dependency.

### MOD-HORO-002: Horoscope Content-Safety Framing

**Phase:** 6 · **Priority:** P0 · **Status:** TODO

Apply a sensitive tone and an "entertainment only" framing/disclaimer.

Acceptance criteria:

- Horoscope content avoids harmful determinism (health/finance guarantees) and includes the entertainment disclaimer.

---

## Operational Requirements

### OPS-001: Cost & Rate-Limit Guardrails

**Phase:** 7 · **Priority:** P1 · **Status:** TODO

LLM + TTS spend multiplies across shows × languages × channels.

Requirements:

- Log per-run LLM/TTS cost and token usage.
- Enforce configurable budget caps; cache identical generations.

Acceptance criteria:

- A runaway loop cannot exceed the configured daily spend cap.

### OPS-002: Observability + Failure Alerting

**Phase:** 7 · **Priority:** P1 · **Status:** TODO

Requirements:

- Per-run metrics dashboard (or structured summary aggregation).
- Alerts on job failures via existing notification channels.

Acceptance criteria:

- An operator is alerted when any scheduled job fails, with enough context to diagnose.

### OPS-003: Multi-Channel Secrets Management

**Phase:** 7 · **Priority:** P1 · **Status:** TODO

Requirements:

- Manage many YouTube OAuth tokens (one per show/channel) securely, out of source control.

Acceptance criteria:

- Adding a new channel's credentials does not risk leaking or overwriting existing tokens.

### OPS-004: YouTube Analytics Feedback Loop

**Phase:** 7 · **Priority:** P2 · **Status:** TODO

Requirements:

- Pull YouTube analytics back to learn which shows/formats/languages perform best.

Acceptance criteria:

- Performance data is available per show to guide content decisions.

### OPS-005: Golden-Output Test Harness

**Phase:** 7 · **Priority:** P1 · **Status:** TODO

Requirements:

- Snapshot tests for script briefs and rendered templates per module.

Acceptance criteria:

- A prompt/template change for one show cannot silently break another; CI flags diffs.

---

## Project Requirements

### PROJ-001: Rename Project to Reflect Scope

**Phase:** 4 · **Priority:** P2 · **Status:** TODO

Rename `gold-price-bot` to a generic name (e.g. `content-engine`, `reel-factory`, `auto-shows`) so the
scope is clear to new contributors.

Acceptance criteria:

- Repo, docs, and references no longer imply gold-only scope.

---

## Implementation Roadmap

Strangler-fig: the gold show keeps working at every step.

| Phase | Theme | Key items |
|-------|-------|-----------|
| 1 | Extract the seam | PLAT-001, PLAT-002, PLAT-003, PLAT-007, MOD-GOLD-001 |
| 2 | Promote the script engine | PLAT-004 |
| 3 | Jobs config + scheduler | PLAT-005, PLAT-006, PLAT-008 |
| 4 | Templates & branding | TMPL-001, TMPL-002, PROJ-001 |
| 5 | Ship Stocks module | MOD-STOCK-001/002/003 |
| 6 | Ship Horoscope module | MOD-HORO-001/002 |
| 7 | Platform hardening | OPS-001…005 |

## Open Questions

1. Where should jobs config live — YAML files in the repo, or a database for non-dev editing?
2. Which stock data provider (NSE direct, Alpha Vantage, a broker API) and what are its rate limits/cost?
3. Should horoscope use pure LLM generation, or an astrology/ephemeris data source for accuracy?
4. One YouTube channel per show, or one per (show × language)?
5. Should each new show be gated behind manual approval until its quality is proven?
6. What is the acceptable daily API spend cap across all shows?
7. Do we batch horoscope into one combined video or 12 per-sign Shorts?
