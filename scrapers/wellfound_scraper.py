from __future__ import annotations
"""
Wellfound scraper with two strategies:
  1. Playwright (headless, with login) — primary
  2. requests + BeautifulSoup on public search — fallback if Playwright fails
"""
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

SOURCE = "Wellfound"
PUBLIC_SEARCH_URL = "https://wellfound.com/jobs"
SEARCH_ROLES = ["backend engineer", "node.js developer", "software engineer"]


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_posted(text: str | None) -> str | None:
    """Convert relative strings like '2 days ago' to approximate ISO timestamps."""
    if not text:
        return None
    from datetime import timedelta
    text = text.lower().strip()
    now = datetime.now(timezone.utc)
    m = re.search(r'(\d+)\s*(minute|hour|day|week|month)', text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta_map = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n),
                 "day": timedelta(days=n), "week": timedelta(weeks=n),
                 "month": timedelta(days=n * 30)}
    return (now - delta_map.get(unit, timedelta())).isoformat()


# ── Strategy 1: Playwright ─────────────────────────────────────────────────

def _scrape_playwright() -> list[dict]:
    email = os.getenv("WELLFOUND_EMAIL", "")
    password = os.getenv("WELLFOUND_PASSWORD", "")
    if not email or not password:
        print(f"[{SOURCE}] Playwright: WELLFOUND_EMAIL/PASSWORD not set — skipping login attempt")
        return []

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print(f"[{SOURCE}] Playwright not installed")
        return []

    results = []
    now = _now_iso()
    print(f"[{SOURCE}] Playwright: launching headless browser...")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = ctx.new_page()

            # Login
            print(f"[{SOURCE}] Playwright: navigating to login...")
            page.goto("https://wellfound.com/login", timeout=30000)
            time.sleep(2)
            page.fill('input[name="user[email]"]', email)
            page.fill('input[name="user[password]"]', password)
            page.click('input[type="submit"], button[type="submit"]')
            page.wait_for_timeout(3000)

            if "login" in page.url:
                print(f"[{SOURCE}] Playwright: login may have failed — continuing anyway")

            # Scrape job search pages
            for role in SEARCH_ROLES:
                try:
                    encoded = requests.utils.quote(role)
                    page.goto(
                        f"https://wellfound.com/jobs?role={encoded}&remote=true",
                        timeout=30000,
                    )
                    page.wait_for_timeout(3000)

                    # Scroll to load more
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, window.innerHeight)")
                        page.wait_for_timeout(1000)

                    html = page.content()
                    results.extend(_parse_wellfound_html(html, now))
                except PWTimeout:
                    print(f"[{SOURCE}] Playwright: timeout for role '{role}'")
                except Exception as e:
                    print(f"[{SOURCE}] Playwright: error for role '{role}' — {e}")
                time.sleep(2)

            browser.close()
    except Exception as e:
        print(f"[{SOURCE}] Playwright: browser error — {e}")
        return []

    # Deduplicate by URL
    seen: set[str] = set()
    unique = []
    for j in results:
        if j["url"] not in seen:
            seen.add(j["url"])
            unique.append(j)
    print(f"[{SOURCE}] Playwright: {len(unique)} unique jobs")
    return unique


# ── Strategy 2: requests + BeautifulSoup (public, no login) ───────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://wellfound.com/",
}


def _parse_wellfound_html(html: str, now: str) -> list[dict]:
    """Parse Wellfound job listing HTML (works for both Playwright + requests output)."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Card selectors — Wellfound uses React so class names vary; try multiple
    cards = (
        soup.select("div[class*='JobListings'] div[class*='mb-6']")
        or soup.select("div[data-test='StartupResult']")
        or soup.select("div[class*='job-listing']")
        or soup.select("div[class*='styles_jobListing']")
    )

    # Fallback: look for anchors pointing to /jobs/
    if not cards:
        links = soup.select("a[href*='/jobs/'][href*='/role']")
        for a in links:
            href = a.get("href", "")
            url = f"https://wellfound.com{href}" if href.startswith("/") else href
            title = a.get_text(strip=True)
            if title and url:
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
        return results

    for card in cards:
        try:
            title_el = card.select_one("h2, h3, [class*='title'], [class*='role']")
            title = title_el.get_text(strip=True) if title_el else ""

            company_el = card.select_one("[class*='company'], [class*='startup'], h4")
            company = company_el.get_text(strip=True) if company_el else ""

            link_el = card.select_one("a[href*='/jobs/']")
            href = link_el["href"] if link_el else ""
            url = f"https://wellfound.com{href}" if href.startswith("/") else href

            salary_el = card.select_one("[class*='salary'], [class*='compensation']")
            salary = salary_el.get_text(strip=True) if salary_el else None

            time_el = card.select_one("time, [class*='time'], [class*='date']")
            posted_raw = time_el.get("datetime") or time_el.get_text(strip=True) if time_el else None
            posted_at = _parse_posted(posted_raw)

            if not url or not title:
                continue

            results.append({
                "title": title,
                "company": company,
                "url": url,
                "salary": salary,
                "location_type": "REMOTE",
                "source": SOURCE,
                "posted_at": posted_at,
                "scraped_at": now,
            })
        except Exception:
            continue

    return results


def _scrape_bs4_fallback() -> list[dict]:
    print(f"[{SOURCE}] Fallback: requests + BeautifulSoup on public search")
    now = _now_iso()
    results = []
    seen_urls: set[str] = set()

    for role in SEARCH_ROLES:
        try:
            r = requests.get(
                PUBLIC_SEARCH_URL,
                params={"role": role, "remote": "true"},
                headers=_HEADERS,
                timeout=20,
            )
            r.raise_for_status()
            items = _parse_wellfound_html(r.text, now)
            print(f"[{SOURCE}] Fallback '{role}' → {len(items)} raw")
            for item in items:
                if item["url"] and item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)
        except Exception as e:
            print(f"[{SOURCE}] Fallback WARNING: '{role}' failed — {e}")
        time.sleep(2)

    print(f"[{SOURCE}] Fallback: {len(results)} unique")
    return results


# ── Public entry point ─────────────────────────────────────────────────────

def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape...")
    results = _scrape_playwright()
    if not results:
        print(f"[{SOURCE}] Playwright returned 0 results — trying BS4 fallback")
        results = _scrape_bs4_fallback()
    return results
