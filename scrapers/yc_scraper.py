from __future__ import annotations
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

SOURCE = "YCombinator"

# HN jobs board — pure HTML, no JS, no auth
HN_JOBS_URL = "https://news.ycombinator.com/jobs"
# Work at a Startup — official YC job board
WAS_URL = "https://www.workatastartup.com/jobs"

KEYWORDS = [
    "backend", "node", "nodejs", "node.js",
    "software engineer", "sde", "software development",
    "backend engineer", "backend developer", "full stack",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
}


def _matches(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in KEYWORDS)


def _parse_hn_age(age_text: str) -> str | None:
    """Convert HN age strings like '3 hours ago' to ISO timestamp."""
    from datetime import timedelta
    import re
    now = datetime.now(timezone.utc)
    m = re.search(r'(\d+)\s*(minute|hour|day|month)', age_text.lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n),
             "day": timedelta(days=n), "month": timedelta(days=n * 30)}.get(unit, timedelta())
    return (now - delta).isoformat()


def _scrape_hn_jobs(now: str) -> list[dict]:
    """Scrape news.ycombinator.com/jobs — straightforward HTML table."""
    results = []
    try:
        r = requests.get(HN_JOBS_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[{SOURCE}] WARNING: HN jobs fetch failed — {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    rows = soup.select("tr.athing")
    print(f"[{SOURCE}] HN: {len(rows)} raw listings")

    for row in rows:
        try:
            title_el = row.select_one(".titleline a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")

            # Skip HN discussion links — we want direct company links
            if not url or url.startswith("item?"):
                # Fall back to the HN item link
                item_id = row.get("id", "")
                if item_id:
                    url = f"https://news.ycombinator.com/item?id={item_id}"

            if not _matches(title):
                continue

            # Age is in the next sibling row
            age_el = row.find_next_sibling("tr")
            age_text = ""
            if age_el:
                age_span = age_el.select_one(".age")
                age_text = age_span.get_text(strip=True) if age_span else ""

            results.append({
                "title": title,
                "company": "",  # HN listings embed company in title
                "url": url if url.startswith("http") else f"https://news.ycombinator.com/{url}",
                "salary": None,
                "location_type": "REMOTE",
                "source": SOURCE,
                "posted_at": _parse_hn_age(age_text),
                "scraped_at": now,
            })
        except Exception:
            continue

    return results


def _scrape_was_api(now: str) -> list[dict]:
    """
    Work at a Startup uses a JSON endpoint for search.
    Falls back gracefully if blocked.
    """
    results = []
    search_terms = ["backend", "node", "software engineer"]

    for term in search_terms:
        try:
            r = requests.get(
                "https://www.workatastartup.com/jobs",
                params={"query": term, "role": "engineer"},
                headers={**HEADERS, "Accept": "application/json, text/html"},
                timeout=20,
            )
            # WAS returns HTML; parse it
            if "application/json" in r.headers.get("content-type", ""):
                data = r.json()
                jobs_raw = data.get("jobs", []) if isinstance(data, dict) else []
                for j in jobs_raw:
                    url = j.get("url") or j.get("link") or ""
                    title = j.get("title") or j.get("name") or ""
                    if not url or not title or not _matches(title):
                        continue
                    results.append({
                        "title": title,
                        "company": j.get("company", {}).get("name", "") if isinstance(j.get("company"), dict) else "",
                        "url": url,
                        "salary": None,
                        "location_type": "REMOTE",
                        "source": SOURCE,
                        "posted_at": None,
                        "scraped_at": now,
                    })
            else:
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select("div[class*='job'], li[class*='job']")
                for card in cards:
                    a = card.select_one("a[href*='/jobs/']")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    url = f"https://www.workatastartup.com{href}" if href.startswith("/") else href
                    if not _matches(title):
                        continue
                    results.append({
                        "title": title,
                        "company": "",
                        "url": url,
                        "salary": None,
                        "location_type": "REMOTE",
                        "source": SOURCE,
                        "posted_at": None,
                        "scraped_at": now,
                    })
        except Exception as e:
            print(f"[{SOURCE}] WARNING: WAS fetch failed for '{term}' — {e}")
        time.sleep(1)

    return results


def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape (HN Jobs + Work at a Startup)...")
    now = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()
    all_results = []

    for item in _scrape_hn_jobs(now) + _scrape_was_api(now):
        if item["url"] and item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            all_results.append(item)

    time.sleep(1)
    print(f"[{SOURCE}] {len(all_results)} unique results")
    return all_results
