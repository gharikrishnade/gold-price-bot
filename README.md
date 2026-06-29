# Gold Price YouTube Bot

Automates regional gold-price videos for YouTube channels. The pipeline scrapes city prices, validates the data, generates a regional-language script, renders a thumbnail, creates voiceover audio, builds a video, and optionally uploads it to YouTube.

## Branch Workflow

- `dev` is the integration branch.
- Create every new change from `dev` on a fresh feature branch.
- Keep secrets, credentials, logs, and generated media out of git.

## Setup

1. Create and activate a virtual environment.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create local environment settings.

```bash
cp .env.example .env
```

3. Fill in `.env`.

Required for script generation:

```bash
ANTHROPIC_API_KEY=...
```

Recommended for TTS:

```bash
SARVAM_API_KEY=...
```

Upload safety defaults:

```bash
YOUTUBE_UPLOAD_PRIVACY=private
```

Paths:

```bash
RUN_OUTPUT_DIR=output/runs
HISTORY_DB_PATH=data/gold_prices.sqlite
SCRAPER_DEBUG_DIR=logs/scraper_debug
LOG_DIR=logs
YOUTUBE_CREDS_DIR=credentials/youtube
```

## YouTube OAuth

1. Create a Google Cloud OAuth client for YouTube Data API v3.
2. Put the client secret at:

```bash
credentials/google_client_secret.json
```

3. Generate each channel token.

```bash
python setup_youtube_auth.py --channel andhra_pradesh
python setup_youtube_auth.py --channel telangana
```

Tokens are stored under `credentials/youtube/` and ignored by git.

To authorize every enabled channel one by one:

```bash
python setup_youtube_auth.py --all
```

## Local Review Workflow

Run a full local generation without upload:

```bash
python main.py --state telangana --dry-run
```

Generate an additional vertical 9:16 MP4 for Shorts/Reels review:

```bash
python main.py --state telangana --dry-run --shorts
```

Generate an animated regional-language trend-card segment when historical prices exist:

```bash
python main.py --state andhra_pradesh --dry-run --trend-cards
```

Generated files are grouped by date and state:

```text
output/runs/YYYY-MM-DD/<state>/
  script.txt
  thumbnail.jpg
  voiceover.mp3
  trend_preview.jpg     # only when --trend-cards has history
  video.mp4
  shorts.mp4            # only when --shorts is used
output/runs/YYYY-MM-DD/summary.json
output/runs/YYYY-MM-DD/review.html
logs/summary_YYYY-MM-DD.json
logs/run_YYYY-MM-DD.log
logs/scraper_debug/YYYY-MM-DD/
```

The summary JSON includes artifact paths, validation status, upload status, video size, optional trend-card and Shorts/Reels status, audio duration, YouTube metadata preview, and errors when present.
Open `output/runs/YYYY-MM-DD/review.html` in a browser for a compact review page with artifact links, thumbnails, optional trend-card preview, optional Shorts/Reels output, and YouTube title/description/tags.
If GoodReturns changes its page structure, the scraper saves failed city HTML and table summaries in `logs/scraper_debug/YYYY-MM-DD/` for diagnosis.

## Uploading

Upload one state using the safe default privacy:

```bash
python main.py --state telangana
```

Choose privacy explicitly:

```bash
python main.py --state telangana --privacy unlisted
python main.py --state telangana --privacy public
```

Require a manual approval marker before upload:

```bash
python main.py --state telangana --require-approval
```

When approval is required, the bot generates all local artifacts, writes `UPLOAD_APPROVAL_REQUIRED.txt` in the state run folder, and skips upload until the marker file exists:

```text
output/runs/YYYY-MM-DD/telangana/APPROVED_FOR_UPLOAD
```

You can also make this the default in `.env`:

```bash
REQUIRE_UPLOAD_APPROVAL=true
UPLOAD_APPROVAL_MARKER=APPROVED_FOR_UPLOAD
```

Use `--no-require-approval` to override that default for a run.

Skip upload even outside dry-run mode:

```bash
python main.py --state andhra_pradesh --skip-upload
```

Skip configured notifications for a local run:

```bash
python main.py --state telangana --dry-run --no-notify
```

The bot records successful uploads in `logs/upload_history.json` and skips duplicate uploads for the same state/date unless you pass:

```bash
python main.py --state telangana --force-upload
```

## Historical Prices

Validated prices are stored in SQLite at `data/gold_prices.sqlite` by default. The script generator only receives comparison data when previous stored prices exist. If history is unavailable, the prompt explicitly forbids price movement and trend language.

## Notifications

Notifications are optional and disabled unless you configure a channel in `.env`.

Slack incoming webhook:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

Telegram bot:

```bash
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

Daily run notifications include completed states, failed states, generated video paths, YouTube links when available, summary paths, and the review page path.
Email via SMTP:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your_email@example.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@example.com
EMAIL_TO=operator@example.com,backup@example.com
```

Daily run notifications include completed states, failed states, generated video paths, YouTube links when available, and summary paths.

## Talking-avatar videos (SadTalker)

A job can render a **lip-synced talking-head** from a single portrait image instead of
the card video — driven by the same regional Sarvam audio. It runs locally via
[SadTalker](https://github.com/OpenTalker/SadTalker) (no per-video cost).

Enable it on a job in `jobs.yaml`:

```yaml
- { id: horoscope-aries, module: horoscope, channel: aries, language: hindi,
    formats: [long, short], video_style: avatar,
    avatar_image: assets/avatars/horoscope_sage.jpg, enabled: false }
```

Setup:

1. Install SadTalker on a machine with a **GPU and a few GB of free disk** (a GPU-less
   laptop is not suitable — CPU renders are very slow). The included helper does the
   clone + venv + deps + checkpoint download and prints the env lines:

   ```bash
   ./setup_sadtalker.sh                 # installs to ./vendor/SadTalker
   # or: ./setup_sadtalker.sh /opt/SadTalker
   ```

   (Or follow SadTalker's own README; keep it in its **own** virtualenv — it pins old
   torch and is happiest on Python 3.10.)
2. Drop your portrait at `assets/avatars/horoscope_sage.jpg` (front-facing, clear face).
3. Point the bot at it via env (the installer prints these):

   ```bash
   SADTALKER_DIR=/path/to/SadTalker
   SADTALKER_PYTHON=/path/to/SadTalker/.venv/bin/python
   SADTALKER_ENHANCER=gfpgan        # optional, sharper but slower
   ```

The talking head is fitted to 1920×1080 (long) or 1080×1920 (Shorts) with a blurred
fill. **If `SADTALKER_DIR` is unset or a render fails, the job automatically falls back
to the standard card video** — nothing breaks. A GPU is strongly recommended; CPU works
but is slow.

## VPS Deployment

The included `setup_vps.sh` installs system dependencies, creates a virtual environment, installs Python dependencies, creates output/log/credential folders, and installs a daily cron job.

Default cron timing:

```cron
0 2 * * * cd /path/to/gold-price-bot && /path/to/gold-price-bot/venv/bin/python main.py >> /path/to/gold-price-bot/logs/cron.log 2>&1
```

That runs at 2:00 AM UTC, which is 7:30 AM IST.

### Per-job scheduling

Jobs are defined in `jobs.yaml`, and each job has its own `schedule` (local `HH:MM`).
Instead of one cron that runs everything at a fixed time, install a single frequent
cron that asks for whatever is *due now*:

```cron
*/15 * * * * cd /path/to/gold-price-bot && /path/to/venv/bin/python main.py --due >> logs/cron.log 2>&1
```

`--due` runs only the enabled jobs whose `schedule` falls within `--window-minutes`
(default 30) of the current time, so a job at `06:30` and a job at `16:00` each fire
at their own time from the same cron. When nothing is due, the run exits cleanly (0).

Inspect the run plan with:

```bash
python main.py --list-jobs
```

Before enabling public publishing on a VPS, run:

```bash
python main.py --dry-run
```

Then review `output/runs/YYYY-MM-DD/summary.json` and the generated videos.
