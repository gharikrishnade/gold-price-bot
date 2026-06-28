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

Generated files are grouped by date and state:

```text
output/runs/YYYY-MM-DD/<state>/
  script.txt
  thumbnail.jpg
  voiceover.mp3
  video.mp4
output/runs/YYYY-MM-DD/summary.json
logs/summary_YYYY-MM-DD.json
logs/run_YYYY-MM-DD.log
logs/scraper_debug/YYYY-MM-DD/
```

The summary JSON includes artifact paths, validation status, upload status, video size, audio duration, and errors when present.
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

Skip upload even outside dry-run mode:

```bash
python main.py --state andhra_pradesh --skip-upload
```

The bot records successful uploads in `logs/upload_history.json` and skips duplicate uploads for the same state/date unless you pass:

```bash
python main.py --state telangana --force-upload
```

## Historical Prices

Validated prices are stored in SQLite at `data/gold_prices.sqlite` by default. The script generator only receives comparison data when previous stored prices exist. If history is unavailable, the prompt explicitly forbids price movement and trend language.

## VPS Deployment

The included `setup_vps.sh` installs system dependencies, creates a virtual environment, installs Python dependencies, creates output/log/credential folders, and installs a daily cron job.

Default cron timing:

```cron
0 2 * * * cd /path/to/gold-price-bot && /path/to/gold-price-bot/venv/bin/python main.py >> /path/to/gold-price-bot/logs/cron.log 2>&1
```

That runs at 2:00 AM UTC, which is 7:30 AM IST.

Before enabling public publishing on a VPS, run:

```bash
python main.py --dry-run
```

Then review `output/runs/YYYY-MM-DD/summary.json` and the generated videos.
