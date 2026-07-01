from __future__ import annotations
"""
Cutshort scraper — uses their public JSON API.
Falls back to BS4 HTML scraping if API is blocked.
"""
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

SOURCE = "Cutshort"

KEYWORDS_SEARCH = ["backend", "nodejs", "software engineer"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://cutshort.io/",
}

# Known Cutshort API endpoints (try in order)
API_ENDPOINTS = [
    "https://cutshort.io/api/public/jobs/search",
    "https://cutshort.io/api/v2/jobs",
    "https://cutshort.io/api/v1/jobs",
]


def _parse_date(val: str | None) -> str | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _scrape_via_api(keyword: str, now: str) -> list[dict]:
    """Try each known API endpoint until one works."""
    for endpoint in API_ENDPOINTS:
        try:
            r = requests.get(
                endpoint,
                params={"q": keyword, "keyword": keyword, "limit": 30, "page": 1},
                headers=HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                continue
            ct = r.headers.get("content-type", "")
            if "application/json" not in ct and "json" not in ct:
                continue
            data = r.json()
            # Cutshort API wraps results in data.jobs or data.results or top-level list
            if isinstance(data, list):
                jobs_raw = data
            elif isinstance(data, dict):
                jobs_raw = (
                    data.get("jobs")
                    or data.get("results")
                    or data.get("data")
                    or []
                )
            else:
                continue
            print(f"[{SOURCE}] API hit: {endpoint} → {len(jobs_raw)} results for '{keyword}'")
            results = []
            for j in jobs_raw:
                url = (
                    j.get("url")
                    or j.get("link")
                    or j.get("jobUrl")
                    or (f"https://cutshort.io/job/{j['id']}" if j.get("id") else "")
                    or (f"https://cutshort.io/job/{j['slug']}" if j.get("slug") else "")
                )
                if not url:
                    continue
                if url.startswith("/"):
                    url = f"https://cutshort.io{url}"
                title = j.get("title") or j.get("designation") or j.get("name") or ""
                company = ""
                c = j.get("company") or j.get("organization") or {}
                if isinstance(c, dict):
                    company = c.get("name") or c.get("title") or ""
                elif isinstance(c, str):
                    company = c
                sal_min = j.get("salaryMin") or j.get("min_salary")
                sal_max = j.get("salaryMax") or j.get("max_salary")
                salary = None
                if sal_min and sal_max:
                    salary = f"₹{int(sal_min)//100000}–{int(sal_max)//100000}L"
                elif sal_min:
                    salary = f"₹{int(sal_min)//100000}L+"
                results.append({
                    "title": title,
                    "company": company,
                    "url": url,
                    "salary": salary,
                    "location_type": "INDIA",
                    "source": SOURCE,
                    "posted_at": _parse_date(j.get("createdAt") or j.get("created_at") or j.get("postedAt")),
                    "scraped_at": now,
                })
            return results
        except Exception as e:
            print(f"[{SOURCE}] API endpoint {endpoint} failed — {e}")
            continue
    return []


def _scrape_via_bs4(keyword: str, now: str) -> list[dict]:
    """HTML fallback — Cutshort server-renders enough for basic extraction."""
    results = []
    try:
        r = requests.get(
            "https://cutshort.io/jobs",
            params={"keyword": keyword, "type": "full-time"},
            headers={**HEADERS, "Accept": "text/html"},
            timeout=20,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[{SOURCE}] BS4 fallback failed for '{keyword}' — {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")

    # Try several card patterns Cutshort has used
    cards = (
        soup.select("div[class*='job-card']")
        or soup.select("div[class*='JobCard']")
        or soup.select("li[class*='job']")
        or soup.select("div[data-testid*='job']")
        or soup.select("div[class*='card'][class*='job']")
    )

    for card in cards:
        try:
            title_el = card.select_one("h2, h3, [class*='title'], [class*='designation']")
            title = title_el.get_text(strip=True) if title_el else ""
            company_el = card.select_one("[class*='company'], [class*='org'], [class*='employer']")
            company = company_el.get_text(strip=True) if company_el else ""
            a_el = card if card.name == "a" else card.select_one("a[href]")
            href = a_el.get("href", "") if a_el else ""
            url = f"https://cutshort.io{href}" if href.startswith("/") else href
            if not url or not title:
                continue
            salary_el = card.select_one("[class*='salary'], [class*='ctc'], [class*='lpa']")
            salary = salary_el.get_text(strip=True) if salary_el else None
            results.append({
                "title": title,
                "company": company,
                "url": url,
                "salary": salary,
                "location_type": "INDIA",
                "source": SOURCE,
                "posted_at": None,
                "scraped_at": now,
            })
        except Exception:
            continue
    return results


def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape (public API → BS4 fallback)...")
    now = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()
    results = []

    for kw in KEYWORDS_SEARCH:
        items = _scrape_via_api(kw, now)
        if not items:
            print(f"[{SOURCE}] API returned nothing for '{kw}' — trying BS4")
            items = _scrape_via_bs4(kw, now)
        print(f"[{SOURCE}] '{kw}' → {len(items)} raw")
        for item in items:
            if item["url"] and item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                results.append(item)
        time.sleep(2)

    print(f"[{SOURCE}] {len(results)} unique results")
    return results
