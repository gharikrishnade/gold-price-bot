# Gold Price Bot Application Improvement Requirements

## Purpose

This document captures recommended improvements for the Gold Price YouTube Bot and converts them into actionable product, engineering, and operational requirements.

The goal is to evolve the bot from a daily automation script into a reliable publishing system that can safely generate, validate, review, and upload regional gold-price videos.

## Current System Summary

The application currently performs the following daily workflow:

1. Scrapes city-wise 22K and 24K gold prices from GoodReturns.
2. Generates regional-language scripts using Anthropic Claude.
3. Generates YouTube thumbnails using Pillow.
4. Generates voiceover audio using gTTS or Google Cloud TTS.
5. Creates videos using MoviePy.
6. Uploads videos to YouTube using per-channel OAuth credentials.

Configured regions include Tamil Nadu, Andhra Pradesh, Telangana, Karnataka, Kerala, Maharashtra, West Bengal, and Delhi/North India.

## Priority Levels

- **P0**: Required before reliable automated publishing.
- **P1**: Strongly recommended for production readiness.
- **P2**: Useful enhancements after core reliability is improved.

## Functional Requirements

### FR-001: Price Data Validation

**Priority:** P0

The system must validate scraped gold price data before script generation, video generation, or upload.

Requirements:

- Validate that each city has both 22K and 24K prices.
- Validate that per-gram and per-10g prices are positive numeric values.
- Reject obviously invalid prices, such as zero values or values outside expected market ranges.
- Mark a state run as failed if required city data is unavailable.
- Log which cities failed validation and why.

Acceptance criteria:

- A state with all prices missing must not generate or upload a video.
- A city with partial data must be reported in the run summary.
- The generated script must not contain zero or placeholder prices.

### FR-002: Historical Price Storage

**Priority:** P1

The system should store daily price data so future scripts can include real comparisons.

Requirements:

- Store scraped prices by date, state, city, karat type, per-gram price, and per-10g price.
- Support lookup of yesterday's prices for comparison.
- Support weekly trend summaries.
- Use a simple durable storage option such as SQLite or structured CSV files.

Acceptance criteria:

- The script generator can safely say whether prices increased, decreased, or remained unchanged compared with the previous available day.
- If historical data is unavailable, the script must avoid comparison language.

### FR-003: State-Specific YouTube Metadata

**Priority:** P0

The system must generate accurate YouTube titles, descriptions, tags, and hashtags per state, not only per language.

Requirements:

- Telugu channels for Andhra Pradesh and Telangana must have separate metadata.
- Metadata must include only the relevant state and city names.
- Metadata templates should support state-specific titles, descriptions, and tags.

Acceptance criteria:

- An Andhra Pradesh video does not describe itself as a Telangana video.
- A Telangana video does not describe itself as an Andhra Pradesh video.
- Each uploaded video title and description match the processed state.

### FR-004: Dry-Run Mode

**Priority:** P0

The application must support running the pipeline without uploading to YouTube.

Requirements:

- Add a CLI option such as `--dry-run`.
- Dry-run mode should scrape, generate script, generate thumbnail, generate audio, and create video.
- Dry-run mode must skip YouTube upload.
- The summary output must clearly indicate that upload was skipped intentionally.

Acceptance criteria:

- Running `python main.py --dry-run` creates local artifacts and does not upload.
- Dry-run results are still written to logs and summary JSON.

### FR-005: Single-State Execution

**Priority:** P0

The application must support running the pipeline for a selected state.

Requirements:

- Add a CLI option such as `--state telangana`.
- Validate that the provided state exists in `CHANNEL_CONFIG`.
- Allow single-state execution together with dry-run mode.

Acceptance criteria:

- Running `python main.py --state tamil_nadu --dry-run` processes only Tamil Nadu.
- Invalid state keys produce a clear error with available options.

### FR-006: Configurable Upload Privacy

**Priority:** P0

The application must support safe upload privacy settings.

Requirements:

- Add a configurable privacy option: `private`, `unlisted`, or `public`.
- Default automated uploads should use `private` or `unlisted`.
- Allow explicit public upload only through configuration or CLI.

Acceptance criteria:

- The upload request uses the configured privacy setting.
- The default configuration does not accidentally publish public videos without review.

### FR-007: Duplicate Upload Protection

**Priority:** P1

The system should prevent duplicate uploads for the same state and date.

Requirements:

- Record completed uploads with state, date, video ID, and URL.
- Before upload, check whether a successful upload already exists for that state and date.
- Allow an explicit override when re-upload is intentional.

Acceptance criteria:

- Re-running the bot for the same state and date does not create a second public upload by default.

### FR-008: Review-Friendly Output

**Priority:** P1

The system should make generated artifacts easy to inspect before upload.

Requirements:

- Store generated script, thumbnail, audio, video, and summary in predictable date-based folders.
- Include paths to all generated artifacts in the summary JSON.
- Provide a clear local review workflow for dry-run outputs.

Acceptance criteria:

- A user can find all artifacts for a given date and state from the summary file.

## Reliability Requirements

### RR-001: Retry Logic

**Priority:** P0

The system must retry transient failures for external services.

Requirements:

- Retry GoodReturns scraping failures.
- Retry Anthropic API failures.
- Retry TTS generation failures where safe.
- Retry YouTube upload chunk failures.
- Use bounded retries with logging.

Acceptance criteria:

- Temporary network failures do not immediately fail the entire daily run.
- Permanent failures are reported clearly after retries are exhausted.

### RR-002: Scraper Resilience

**Priority:** P0

The scraper must handle source HTML changes safely.

Requirements:

- Save debug information when parsing fails.
- Include source URL in scrape results or logs.
- Treat missing tables or changed selectors as validation failures.
- Avoid silently returning incomplete price data as success.

Acceptance criteria:

- If GoodReturns changes its page structure, the run fails safely instead of publishing incorrect prices.

### RR-003: Font and Rendering Checks

**Priority:** P1

The system should verify required fonts before thumbnail generation.

Requirements:

- Check for required Noto fonts for all enabled languages.
- Report missing fonts clearly.
- Provide fallback behavior only when output quality remains acceptable.

Acceptance criteria:

- Missing regional fonts are detected before thumbnails are generated.
- Thumbnail text does not render as boxes or unreadable fallback glyphs.

### RR-004: Thumbnail Layout Robustness

**Priority:** P1

Thumbnail rendering must handle long text safely.

Requirements:

- Prevent city names, titles, and regional-language labels from overflowing.
- Support dynamic font sizing or text wrapping.
- Validate that price cards remain readable.

Acceptance criteria:

- Long state names or city names do not overlap other thumbnail elements.

## Operational Requirements

### OR-001: Structured Run Summary

**Priority:** P0

The system must write a complete machine-readable summary for every run.

Required fields:

- Run date and timestamp.
- State key and language.
- Scrape status.
- Price validation status.
- Script generation status.
- Thumbnail path.
- Audio path.
- Audio duration.
- Video path.
- Video size.
- Upload status.
- YouTube video ID and URL when available.
- Error details when failed.

Acceptance criteria:

- Each run produces a JSON summary that can be used for monitoring or debugging.

### OR-002: Better Logging

**Priority:** P0

The system must produce logs that are useful during failures.

Requirements:

- Include stack traces for unexpected exceptions.
- Include external source URLs for scraping.
- Include API step names and state keys in log messages.
- Separate expected validation errors from unexpected runtime errors.

Acceptance criteria:

- A failed run can be diagnosed from logs without rerunning in debug mode.

### OR-003: Deployment Documentation

**Priority:** P1

The project must include clear setup and deployment documentation.

Requirements:

- Document required environment variables.
- Document YouTube OAuth setup.
- Document local dry-run usage.
- Document VPS deployment.
- Document cron schedule.
- Document where outputs, logs, and credentials are stored.

Acceptance criteria:

- A new operator can set up and test the bot using the documentation.

### OR-004: Notification After Daily Run

**Priority:** P2

The system should notify the operator after daily runs.

Possible channels:

- Email.
- Telegram.
- WhatsApp.
- Slack.

Notification should include:

- Successful states.
- Failed states.
- Generated video paths.
- YouTube links.
- Summary file path.

Acceptance criteria:

- The operator receives a concise success or failure report after the scheduled run.

## Safety Requirements

### SR-001: Safe Defaults

**Priority:** P0

The system must avoid public publishing unless explicitly configured.

Requirements:

- Default upload privacy should be `private` or `unlisted`.
- Dry-run should be easy to use.
- Public upload should be an intentional choice.

Acceptance criteria:

- A first-time run cannot accidentally publish videos publicly without configuration.

### SR-002: Secret Handling

**Priority:** P0

The system must keep API keys and OAuth credentials out of source control.

Requirements:

- Continue using `.env` for local secrets.
- Keep YouTube OAuth tokens under `credentials/youtube`.
- Add or verify `.gitignore` entries for `.env`, credentials, logs, generated videos, audio, and thumbnails.
- Never write secrets to logs.

Acceptance criteria:

- Generated artifacts and credentials are not committed accidentally.

## Content Quality Requirements

### CQR-001: Script Accuracy

**Priority:** P0

Generated scripts must only reference verified data.

Requirements:

- Do not fabricate price movement comparisons.
- Use historical comparison only when stored historical data exists.
- Include date, state, and city names accurately.
- Avoid mixing wrong regional references.

Acceptance criteria:

- Script text only contains prices and comparisons backed by available data.

### CQR-002: Better Video Presentation

**Priority:** P2

The video format should be improved beyond a static thumbnail zoom.

Potential enhancements:

- Add animated price cards.
- Add subtle background music.
- Add intro and outro branding.
- Add simple trend charts when historical data is available.
- Create short vertical versions for YouTube Shorts and Instagram Reels.

Acceptance criteria:

- Generated videos feel more dynamic while preserving price readability.

## Suggested CLI Interface

The improved application should support commands similar to:

```bash
python main.py --dry-run
python main.py --state telangana --dry-run
python main.py --state tamil_nadu --privacy private
python main.py --state andhra_pradesh --skip-upload
python main.py --state kerala --force-upload
```

## Suggested Implementation Roadmap

### Phase 1: Publishing Safety

Priority: P0

- Add CLI options for `--dry-run`, `--state`, and `--privacy`.
- Add price validation.
- Change default upload privacy to private or unlisted.
- Add state-specific YouTube metadata.
- Improve summary JSON and logging.

### Phase 2: Reliability

Priority: P0/P1

- Add retry logic.
- Improve scraper failure handling.
- Add duplicate upload protection.
- Add font checks.
- Add thumbnail overflow handling.

### Phase 3: Content Intelligence

Priority: P1/P2

- Add historical price storage.
- Generate real day-over-day and weekly comparisons.
- Add charts or animated overlays.
- Add review-friendly artifact organization.

### Phase 4: Operations

Priority: P1/P2

- Add setup and deployment documentation.
- Add daily run notifications.
- Add optional dashboard or review page.
- Add Shorts/Reels output mode.

## Open Questions

1. Should the default upload privacy be `private` or `unlisted`?
2. Should historical price storage use SQLite or CSV files?
3. Should generated videos require manual approval before upload?
4. Should each state have a separate YouTube channel or can multiple states share one channel?
5. Should HeyGen avatar videos remain optional, or become the primary video format later?

