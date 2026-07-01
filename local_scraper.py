from __future__ import annotations
#!/usr/bin/env python3
"""
Local scraper — runs on your Mac (residential IP).
Adds Wellfound + Cutshort (shared Playwright browser) and Naukri + Google (JobSpy).
Everything else mirrors main.py exactly.

Usage:
    cd job_scraper
    python local_scraper.py
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv()

from filters import apply_filters
from deduplicator import load_seen, save_seen, deduplicate
from notifier import send_digest
import dashboard_generator

from scrapers import (
    jobspy_scraper,       # Naukri + Google — works on residential IP
    remoteok_scraper,
    himalayas_scraper,
    remotive_scraper,
    rss_scraper,
    yc_scraper,
)
from scrapers.browser_scrapers import scrape_local_browser  # Wellfound + Cutshort

JOBS_FILE = os.path.join(os.path.dirname(__file__), "jobs.json")
WINDOW_DAYS = 7


def run_scraper(name: str, fn):
    try:
        results = fn()
        print(f"[{name}] {len(results)} raw results")
        return results
    except Exception as e:
        print(f"[{name}] ERROR: {e}", file=sys.stderr)
        return []


def load_jobs() -> dict:
    if not os.path.exists(JOBS_FILE):
        return {"last_updated": None, "total_count": 0, "jobs": []}
    with open(JOBS_FILE) as f:
        return json.load(f)


def save_jobs(data: dict) -> None:
    with open(JOBS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def prune_old_jobs(jobs: list[dict]) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    kept = []
    for j in jobs:
        scraped = j.get("scraped_at")
        if not scraped:
            kept.append(j)
            continue
        try:
            dt = datetime.fromisoformat(scraped.replace("Z", "+00:00"))
            if dt >= cutoff:
                kept.append(j)
        except Exception:
            kept.append(j)
    return kept


def main():
    print("=" * 60)
    print(f"[Local] Job scraper started at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    all_raw: list[dict] = []

    # ── Local-only sources ─────────────────────────────────────────
    # JobSpy works on residential IP (CAPTCHA'd on CI)
    all_raw.extend(run_scraper("JobSpy", jobspy_scraper.scrape))

    # Wellfound (cookie auth) + Cutshort (Playwright) — one shared browser
    all_raw.extend(run_scraper("BrowserScraper", scrape_local_browser))

    # ── Same sources as CI ─────────────────────────────────────────
    all_raw.extend(run_scraper("RemoteOK", remoteok_scraper.scrape))
    all_raw.extend(run_scraper("Himalayas", himalayas_scraper.scrape))
    all_raw.extend(run_scraper("Remotive", remotive_scraper.scrape))
    all_raw.extend(run_scraper("RSS", rss_scraper.scrape))
    all_raw.extend(run_scraper("YCombinator", yc_scraper.scrape))

    print(f"\n[Local] Total raw: {len(all_raw)}")

    filtered = apply_filters(all_raw)
    print(f"[Local] After filters: {len(filtered)}")

    seen = load_seen()
    new_jobs, new_urls = deduplicate(filtered, seen)
    print(f"[Local] New (not seen before): {len(new_jobs)}")

    seen.update(new_urls)
    save_seen(seen)

    # Strip description before persisting — used only for filtering, bloats JSON
    for j in new_jobs:
        j.pop("description", None)

    jobs_data = load_jobs()
    existing = jobs_data.get("jobs", [])
    combined = existing + new_jobs
    pruned = prune_old_jobs(combined)
    now_iso = datetime.now(timezone.utc).isoformat()
    jobs_data = {
        "last_updated": now_iso,
        "total_count": len(pruned),
        "jobs": pruned,
    }
    save_jobs(jobs_data)
    print(f"[Local] jobs.json: {len(pruned)} total ({len(new_jobs)} added)")

    dashboard_generator.generate()

    if new_jobs:
        dashboard_url = os.getenv("DASHBOARD_URL", "https://ayushworkk07.github.io/job-scraper")
        send_digest(new_jobs, dashboard_url)
    else:
        print("[Local] No new jobs — skipping Telegram digest")

    print("\n" + "=" * 60)
    print("[Local] Run summary:")
    source_counts: dict[str, dict] = {}
    for j in all_raw:
        s = j.get("source", "Unknown")
        source_counts.setdefault(s, {"raw": 0, "new": 0})
        source_counts[s]["raw"] += 1
    for j in new_jobs:
        s = j.get("source", "Unknown")
        source_counts.setdefault(s, {"raw": 0, "new": 0})
        source_counts[s]["new"] += 1
    for src, counts in sorted(source_counts.items()):
        print(f"  [{src}] {counts['raw']} raw → {counts['new']} new")
    print(f"  TOTAL: {len(all_raw)} raw → {len(filtered)} filtered → {len(new_jobs)} new")
    print("=" * 60)


if __name__ == "__main__":
    main()
