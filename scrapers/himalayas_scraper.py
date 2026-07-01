from __future__ import annotations
import time
import requests
from datetime import datetime, timezone

SOURCE = "Himalayas"
BASE_URL = "https://himalayas.app/jobs/api/search"
SEARCH_TERMS = ["backend engineer", "node.js", "software engineer"]


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
            url = job.get("url") or job.get("applicationUrl") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            salary = job.get("salary") or job.get("salaryRange") or None
            if isinstance(salary, dict):
                lo = salary.get("min")
                hi = salary.get("max")
                currency = salary.get("currency", "USD")
                if lo and hi:
                    salary = f"{currency} {lo:,}–{hi:,}"
                elif lo:
                    salary = f"{currency} {lo:,}+"
                else:
                    salary = None

            results.append({
                "title": job.get("title", ""),
                "company": job.get("company", {}).get("name", "") if isinstance(job.get("company"), dict) else job.get("company", ""),
                "url": url,
                "salary": str(salary) if salary else None,
                "location_type": "REMOTE",
                "source": SOURCE,
                "posted_at": _parse_date(job.get("createdAt") or job.get("publishedAt")),
                "scraped_at": now,
            })

        time.sleep(1)

    print(f"[{SOURCE}] {len(results)} total unique results")
    return results
