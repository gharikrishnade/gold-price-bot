#!/bin/bash
# setup_vps.sh — One-time VPS setup for Gold Price Bot
# Run as root or with sudo on Ubuntu 22.04

set -e

echo "=== Gold Price Bot VPS Setup ==="

# 1. System dependencies
echo "[1/6] Installing system packages + Noto fonts for all Indian scripts..."
apt-get update -q
apt-get install -y python3 python3-pip python3-venv git cron \
  fonts-noto-core \
  fonts-noto-extra \
  fonts-noto-ui-core \
  fonts-noto-cjk \
  fonts-noto-color-emoji
# Ensure font cache is updated
fc-cache -fv &>/dev/null

# 2. Clone / navigate to project
echo "[2/6] Setting up project directory..."
PROJECT_DIR="/opt/gold-price-bot"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# (If you're using git, uncomment:)
# git clone https://github.com/YOUR_USERNAME/gold-price-bot.git .

# 3. Python virtual environment
echo "[3/6] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create directories
echo "[4/6] Creating required directories..."
mkdir -p output/videos logs credentials/youtube

# 5. Set up .env
echo "[5/6] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  ⚠️  Edit .env with your API keys before running!"
fi

# 6. Set up cron job (runs at 7:30 AM IST daily)
# IST = UTC+5:30, so 7:30 IST = 2:00 UTC
echo "[6/6] Setting up daily cron job (7:30 AM IST = 2:00 AM UTC)..."
CRON_JOB="0 2 * * * cd $PROJECT_DIR && $PROJECT_DIR/venv/bin/python main.py >> $PROJECT_DIR/logs/cron.log 2>&1"

# Add to crontab if not already there
(crontab -l 2>/dev/null | grep -v "gold-price-bot"; echo "$CRON_JOB") | crontab -

echo ""
echo "=== Setup Complete ==="
echo ""
echo "NEXT STEPS:"
echo "  1. Edit .env with your API keys:"
echo "     nano $PROJECT_DIR/.env"
echo ""
echo "  2. Add your Google OAuth client secret:"
echo "     Upload to: $PROJECT_DIR/credentials/google_client_secret.json"
echo ""
echo "  3. Authorize each YouTube channel (run on a machine with a browser):"
echo "     python setup_youtube_auth.py --all"
echo "     Then upload credentials/youtube/*.json to the VPS"
echo ""
echo "  4. Test a single run:"
echo "     cd $PROJECT_DIR && source venv/bin/activate && python main.py"
echo ""
echo "  5. Cron is set for 7:30 AM IST (2:00 AM UTC) daily."
echo "     Check: crontab -l"
echo ""
