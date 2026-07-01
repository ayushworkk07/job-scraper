from __future__ import annotations
import time
import requests
from datetime import datetime, timezone

SOURCE = "Remotive"
API_URL = "https://remotive.com/api/remote-jobs"

KEYWORDS = ["backend", "node", "nodejs", "software engineer", "sde", "software development"]


def _matches(job: dict) -> bool:
    text = " ".join([
        job.get("title", ""),
        job.get("description", ""),
        job.get("candidate_required_location", ""),
    ]).lower()
    return any(kw in text for kw in KEYWORDS)


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape...")
    try:
        r = requests.get(
            API_URL,
            params={"category": "software-dev", "limit": 100},
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[{SOURCE}] WARNING: fetch failed — {e}")
        return []

    listings = data.get("jobs", []) if isinstance(data, dict) else []
    print(f"[{SOURCE}] {len(listings)} raw listings")

    results = []
    now = datetime.now(timezone.utc).isoformat()
    for job in listings:
        if not _matches(job):
            continue
        results.append({
            "title": job.get("title", ""),
            "company": job.get("company_name", ""),
            "url": job.get("url", ""),
            "salary": job.get("salary") or None,
            "location_type": "REMOTE",
            "source": SOURCE,
            "posted_at": _parse_date(job.get("publication_date")),
            "scraped_at": now,
        })

    time.sleep(1)
    print(f"[{SOURCE}] {len(results)} passed keyword filter")
    return results
