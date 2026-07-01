from __future__ import annotations
import time
from datetime import datetime, timezone

SOURCE_INDEED = "Indeed"
SOURCE_LINKEDIN = "LinkedIn"

SEARCH_TERMS = [
    "backend engineer",
    "nodejs developer",
    "software engineer",
    "SDE backend",
]


def _try_import():
    try:
        from jobspy import scrape_jobs
        return scrape_jobs
    except ImportError:
        return None


def _to_iso(dt_val) -> str | None:
    if dt_val is None:
        return None
    try:
        if hasattr(dt_val, "isoformat"):
            if dt_val.tzinfo is None:
                return dt_val.replace(tzinfo=timezone.utc).isoformat()
            return dt_val.astimezone(timezone.utc).isoformat()
        return str(dt_val)
    except Exception:
        return None


def _determine_location_type(location: str | None) -> str:
    if not location:
        return "INDIA"
    loc = location.lower()
    if any(w in loc for w in ("remote", "anywhere", "worldwide")):
        return "REMOTE"
    return "INDIA"


def _scrape_site(scrape_jobs_fn, site: str, term: str, now: str) -> list[dict]:
    source = SOURCE_INDEED if site == "indeed" else SOURCE_LINKEDIN
    try:
        df = scrape_jobs_fn(
            site_name=[site],
            search_term=term,
            location="India",
            results_wanted=25,
            country_indeed="India",
            hours_old=72,
        )
        if df is None or df.empty:
            return []

        results = []
        for _, row in df.iterrows():
            url = str(row.get("job_url") or row.get("url") or "")
            if not url:
                continue

            salary_parts = []
            if row.get("min_amount"):
                salary_parts.append(str(row["min_amount"]))
            if row.get("max_amount"):
                salary_parts.append(str(row["max_amount"]))
            salary_interval = str(row.get("currency") or "")
            salary = None
            if salary_parts:
                salary = f"{salary_interval} {'-'.join(salary_parts)}".strip()

            results.append({
                "title": str(row.get("title") or ""),
                "company": str(row.get("company") or ""),
                "url": url,
                "salary": salary or None,
                "location_type": _determine_location_type(str(row.get("location") or "")),
                "source": source,
                "posted_at": _to_iso(row.get("date_posted")),
                "scraped_at": now,
            })
        return results
    except Exception as e:
        print(f"[{source}] WARNING: scrape_jobs failed for '{term}' on {site} — {e}")
        return []


def scrape() -> list[dict]:
    print(f"[JobSpy] Starting Indeed + LinkedIn scrape...")
    scrape_jobs_fn = _try_import()
    if scrape_jobs_fn is None:
        print("[JobSpy] WARNING: python-jobspy not installed — skipping")
        return []

    now = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()
    results = []

    for site in ("indeed", "linkedin"):
        source_label = SOURCE_INDEED if site == "indeed" else SOURCE_LINKEDIN
        site_results = []
        for term in SEARCH_TERMS:
            items = _scrape_site(scrape_jobs_fn, site, term, now)
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    site_results.append(item)
            time.sleep(3)
        print(f"[{source_label}] {len(site_results)} unique results")
        results.extend(site_results)

    return results
