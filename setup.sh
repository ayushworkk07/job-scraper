#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.job_scraper_venv"
PLIST_NAME="com.ayush.job_scraper"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Job Scraper Setup ==="

# 1. Create venv (requires Python 3.10+ for python-jobspy)
PYTHON311="/opt/homebrew/bin/python3.11"
if [ ! -f "$PYTHON311" ]; then
  echo "ERROR: Python 3.11 not found at $PYTHON311"
  echo "Run: brew install python@3.11"
  exit 1
fi
if [ ! -d "$VENV" ]; then
  echo "Creating venv at $VENV (Python 3.11)..."
  "$PYTHON311" -m venv "$VENV"
else
  echo "Venv already exists at $VENV — recreating with Python 3.11..."
  rm -rf "$VENV"
  "$PYTHON311" -m venv "$VENV"
fi

# 2. Install dependencies
echo "Installing dependencies..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"

# 3. Install Playwright browser
echo "Installing Playwright chromium..."
"$VENV/bin/playwright" install chromium

# 4. Write .env if missing
ENV_FILE="$SCRIPT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Writing .env..."
  cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=8651873660:AAFHwlORjIKPRhfX02KX0e1NrKF8lUa9u44
TELEGRAM_CHAT_ID=880309027
DASHBOARD_URL=https://ayushworkk07.github.io/job-scraper
EOF
  echo ".env created."
else
  echo ".env already exists — skipping."
fi

# 5. Register launchd daemon
echo "Registering launchd daemon..."
launchctl unload "$PLIST_DEST" 2>/dev/null || true
cp "$SCRIPT_DIR/com.ayush.job_scraper.plist" "$PLIST_DEST"
launchctl load "$PLIST_DEST"

echo ""
echo "=== Setup complete ==="
echo "Job scraper will run every 30 minutes automatically."
echo "It will also run once right now (check logs in ~30s)."
echo ""
echo "Useful commands:"
echo "  bash manage.sh logs     — live log stream"
echo "  bash manage.sh errors   — live error stream"
echo "  bash manage.sh status   — check if running"
echo "  bash manage.sh stop     — stop the daemon"
echo "  bash manage.sh run      — run once manually"
