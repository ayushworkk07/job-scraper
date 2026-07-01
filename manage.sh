#!/usr/bin/env bash
# manage.sh — control the job scraper launchd daemon

PLIST_NAME="com.ayush.job_scraper"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/com.ayush.job_scraper.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
LOG_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$1" in
  start)
    cp "$PLIST_SRC" "$PLIST_DEST"
    launchctl load "$PLIST_DEST"
    echo "Job scraper started (runs every 2 hours)."
    ;;
  stop)
    launchctl unload "$PLIST_DEST" 2>/dev/null
    echo "Job scraper stopped."
    ;;
  restart)
    launchctl unload "$PLIST_DEST" 2>/dev/null
    sleep 1
    cp "$PLIST_SRC" "$PLIST_DEST"
    launchctl load "$PLIST_DEST"
    echo "Job scraper restarted."
    ;;
  status)
    launchctl list | grep "$PLIST_NAME" || echo "Not running."
    ;;
  logs)
    tail -f "$LOG_DIR/launchd_stdout.log"
    ;;
  errors)
    tail -f "$LOG_DIR/launchd_stderr.log"
    ;;
  run)
    echo "Running local_scraper.py once now..."
    /Users/ayushdabas/.job_scraper_venv/bin/python3 "$LOG_DIR/local_scraper.py"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs|errors|run}"
    exit 1
    ;;
esac
