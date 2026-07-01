from __future__ import annotations
import os
import re
import requests
from datetime import datetime, timezone


def _escape(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    special = r'\_*[]()~`>#+-=|{}.!'
    return re.sub(r'([' + re.escape(special) + r'])', r'\\\1', str(text))


def _humanize_salary(salary: str | None) -> str:
    if not salary:
        return "Not listed"
    return salary


def _source_counts(jobs: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for j in jobs:
        s = j.get("source", "Unknown")
        counts[s] = counts.get(s, 0) + 1
    return counts


def _top_jobs(jobs: list[dict], n: int = 3) -> list[dict]:
    def sort_key(j):
        posted = j.get("posted_at") or ""
        try:
            return datetime.fromisoformat(posted.replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    return sorted(jobs, key=sort_key, reverse=True)[:n]


def send_digest(new_jobs: list[dict], dashboard_url: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[Notifier] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — skipping")
        return False
    if not new_jobs:
        print("[Notifier] 0 new jobs — skipping digest")
        return False

    counts = _source_counts(new_jobs)
    source_line = " · ".join(f"{s}: {c}" for s, c in sorted(counts.items()))

    top = _top_jobs(new_jobs)
    top_lines = []
    for i, j in enumerate(top, 1):
        title = _escape(j.get("title", "N/A"))
        company = _escape(j.get("company", "N/A"))
        source = _escape(j.get("source", ""))
        salary = _escape(_humanize_salary(j.get("salary")))
        url = j.get("url", "")
        top_lines.append(f"{i}\\. {title} @ {company} · {source} · {salary} → [link]({url})")

    total = len(new_jobs)
    dashboard_escaped = _escape(dashboard_url)

    msg = (
        f"⚡ *Job Scan Complete*\n\n"
        f"📊 *{total} new jobs found*\n"
        f"{_escape(source_line)}\n\n"
        f"🔥 *Top {len(top)} by recency:*\n"
        + "\n".join(top_lines)
        + f"\n\n📋 [Open Dashboard]({dashboard_url})"
    )

    url_api = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url_api, json=payload, timeout=15)
        r.raise_for_status()
        print(f"[Notifier] Digest sent — {total} jobs")
        return True
    except Exception as e:
        print(f"[Notifier] Failed to send Telegram message: {e}")
        return False
