from __future__ import annotations
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

SOURCE = "Cutshort"
SEARCH_URL = "https://cutshort.io/jobs"
KEYWORDS_PARAM = ["backend", "nodejs", "software-engineer"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _scrape_keyword(keyword: str, now: str) -> list[dict]:
    results = []
    try:
        r = requests.get(
            SEARCH_URL,
            params={"keyword": keyword, "type": "full-time"},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[{SOURCE}] WARNING: fetch failed for '{keyword}' — {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")

    # Cutshort job cards — selectors may need updates if site changes
    cards = soup.select("div.job-card, div[class*='JobCard'], li[class*='job-item']")
    if not cards:
        # Fallback: look for anchor tags with /jobs/ pattern
        cards = soup.select("a[href*='/jobs/']")

    for card in cards:
        try:
            # Title
            title_el = card.select_one(
                "h2, h3, [class*='title'], [class*='job-title'], [class*='position']"
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Company
            company_el = card.select_one(
                "[class*='company'], [class*='org'], [class*='employer']"
            )
            company = company_el.get_text(strip=True) if company_el else ""

            # URL
            link_el = card if card.name == "a" else card.select_one("a[href]")
            href = link_el["href"] if link_el else ""
            url = f"https://cutshort.io{href}" if href.startswith("/") else href

            if not url or not title:
                continue

            # Salary
            salary_el = card.select_one(
                "[class*='salary'], [class*='pay'], [class*='ctc'], [class*='lpa']"
            )
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
    print(f"[{SOURCE}] Starting scrape...")
    now = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()
    results = []

    for kw in KEYWORDS_PARAM:
        items = _scrape_keyword(kw, now)
        print(f"[{SOURCE}] '{kw}' → {len(items)} raw")
        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                results.append(item)
        time.sleep(2)

    print(f"[{SOURCE}] {len(results)} unique results")
    return results
