from __future__ import annotations
import time
import requests
from datetime import datetime, timezone

SOURCE = "RemoteOK"
API_URL = "https://remoteok.com/api"

KEYWORDS = ["backend", "node", "software engineer", "sde", "software development"]


def _matches(job: dict) -> bool:
    text = " ".join([
        job.get("position", ""),
        job.get("description", ""),
        " ".join(job.get("tags", [])),
    ]).lower()
    return any(kw in text for kw in KEYWORDS)


def _parse_date(epoch) -> str | None:
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except Exception:
        return None


def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape...")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; job-scraper/1.0)"}
    try:
        r = requests.get(API_URL, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[{SOURCE}] WARNING: fetch failed — {e}")
        return []

    # First element is metadata
    listings = [item for item in data if isinstance(item, dict) and "position" in item]
    print(f"[{SOURCE}] {len(listings)} found")

    results = []
    now = datetime.now(timezone.utc).isoformat()
    for job in listings:
        if not _matches(job):
            continue
        salary = None
        if job.get("salary_min") and job.get("salary_max"):
            lo = int(job["salary_min"])
            hi = int(job["salary_max"])
            salary = f"${lo:,}–${hi:,}"
        elif job.get("salary_min"):
            salary = f"${int(job['salary_min']):,}+"

        results.append({
            "title": job.get("position", ""),
            "company": job.get("company", ""),
            "url": job.get("url") or f"https://remoteok.com/remote-jobs/{job.get('id', '')}",
            "salary": salary,
            "location_type": "REMOTE",
            "source": SOURCE,
            "posted_at": _parse_date(job.get("epoch")),
            "scraped_at": now,
        })

    time.sleep(1)
    print(f"[{SOURCE}] {len(results)} passed keyword filter")
    return results
