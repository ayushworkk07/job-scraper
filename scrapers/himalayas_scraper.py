from __future__ import annotations
import time
import requests
from datetime import datetime, timezone

SOURCE = "Himalayas"
BASE_URL = "https://himalayas.app/jobs/api/search"
SEARCH_TERMS = ["backend engineer", "node.js", "software engineer"]


def _parse_date(val) -> str | None:
    if not val:
        return None
    try:
        # pubDate is a Unix timestamp integer
        return datetime.fromtimestamp(int(val), tz=timezone.utc).isoformat()
    except Exception:
        return None


def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape...")
    seen_urls: set[str] = set()
    results = []
    now = datetime.now(timezone.utc).isoformat()

    for term in SEARCH_TERMS:
        try:
            r = requests.get(
                BASE_URL,
                params={"q": term, "limit": 50},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[{SOURCE}] WARNING: fetch failed for '{term}' — {e}")
            time.sleep(1)
            continue

        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        print(f"[{SOURCE}] '{term}' → {len(jobs)} raw")

        for job in jobs:
            # API uses applicationLink or guid for the job URL
            url = (
                job.get("applicationLink")
                or job.get("guid")
                or job.get("url")
                or ""
            )
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            salary = None
            lo = job.get("minSalary")
            hi = job.get("maxSalary")
            currency = job.get("currency") or "USD"
            if lo and hi:
                salary = f"{currency} {int(lo):,}–{int(hi):,}"
            elif lo:
                salary = f"{currency} {int(lo):,}+"

            results.append({
                "title": job.get("title", ""),
                "company": job.get("companyName", ""),
                "url": url,
                "salary": salary,
                "location_type": "REMOTE",
                "source": SOURCE,
                "posted_at": _parse_date(job.get("pubDate")),
                "scraped_at": now,
            })

        time.sleep(1)

    print(f"[{SOURCE}] {len(results)} total unique results")
    return results
