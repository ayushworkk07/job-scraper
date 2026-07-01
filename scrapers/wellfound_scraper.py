from __future__ import annotations
"""
Wellfound scraper — cookie-based Playwright auth.

Setup (one-time):
  1. Install "Cookie-Editor" extension in Chrome
  2. Log into wellfound.com
  3. Click Cookie-Editor → Export → Export as JSON → copy
  4. Save to wellfound_cookies.json in the project root (local dev)
  5. For GitHub Actions: base64-encode the file and store as secret WELLFOUND_COOKIES
     macOS:  base64 -i wellfound_cookies.json | pbcopy
     Linux:  base64 -w 0 wellfound_cookies.json
     Then add as GitHub secret — the workflow decodes it back to the file.

When cookies expire you'll see:
  [Wellfound] Cookies expired or invalid — re-export from Chrome
"""
import json
import os
import re
import time
from datetime import datetime, timezone

SOURCE = "Wellfound"
COOKIES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wellfound_cookies.json")
SEARCH_ROLES = ["backend engineer", "node.js", "software engineer"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_posted(text: str | None) -> str | None:
    if not text:
        return None
    from datetime import timedelta
    text = text.lower().strip()
    now = datetime.now(timezone.utc)
    m = re.search(r'(\d+)\s*(minute|hour|day|week|month)', text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {
        "minute": timedelta(minutes=n), "hour": timedelta(hours=n),
        "day": timedelta(days=n), "week": timedelta(weeks=n),
        "month": timedelta(days=n * 30),
    }.get(unit, timedelta())
    return (now - delta).isoformat()


def _load_cookies() -> list[dict] | None:
    """Load cookies from wellfound_cookies.json. Returns None if file missing."""
    if not os.path.exists(COOKIES_FILE):
        print(f"[{SOURCE}] wellfound_cookies.json not found — skipping")
        return None
    try:
        with open(COOKIES_FILE) as f:
            raw = json.load(f)
        # Cookie-Editor exports as list of objects; Playwright needs name/value/domain/path
        cookies = []
        for c in raw:
            entry: dict = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ".wellfound.com"),
                "path": c.get("path", "/"),
            }
            if not entry["name"] or not entry["value"]:
                continue
            if c.get("secure"):
                entry["secure"] = True
            if c.get("httpOnly"):
                entry["httpOnly"] = True
            if c.get("expirationDate"):
                entry["expires"] = int(c["expirationDate"])
            elif c.get("expires") and isinstance(c["expires"], (int, float)):
                entry["expires"] = int(c["expires"])
            cookies.append(entry)
        if not cookies:
            print(f"[{SOURCE}] wellfound_cookies.json is empty or malformed — skipping")
            return None
        return cookies
    except Exception as e:
        print(f"[{SOURCE}] Failed to load cookies — {e}")
        return None


def _parse_html(html: str, now: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    results = []

    cards = (
        soup.select("div[class*='JobListings'] div[class*='mb-6']")
        or soup.select("div[data-test='StartupResult']")
        or soup.select("div[class*='job-listing']")
        or soup.select("div[class*='styles_jobListing']")
    )

    if not cards:
        for a in soup.select("a[href*='/jobs/'][href*='/role']"):
            href = a.get("href", "")
            url = f"https://wellfound.com{href}" if href.startswith("/") else href
            title = a.get_text(strip=True)
            if title and url:
                results.append({
                    "title": title, "company": "", "url": url,
                    "salary": None, "location_type": "REMOTE",
                    "source": SOURCE, "posted_at": None, "scraped_at": now,
                })
        return results

    for card in cards:
        try:
            title_el = card.select_one("h2, h3, [class*='title'], [class*='role']")
            title = title_el.get_text(strip=True) if title_el else ""
            company_el = card.select_one("[class*='company'], [class*='startup'], h4")
            company = company_el.get_text(strip=True) if company_el else ""
            a = card.select_one("a[href*='/jobs/']")
            href = a["href"] if a else ""
            url = f"https://wellfound.com{href}" if href.startswith("/") else href
            salary_el = card.select_one("[class*='salary'], [class*='compensation']")
            salary = salary_el.get_text(strip=True) if salary_el else None
            time_el = card.select_one("time, [class*='time'], [class*='date']")
            posted_raw = (time_el.get("datetime") or time_el.get_text(strip=True)) if time_el else None
            if not url or not title:
                continue
            results.append({
                "title": title, "company": company, "url": url,
                "salary": salary, "location_type": "REMOTE",
                "source": SOURCE, "posted_at": _parse_posted(posted_raw), "scraped_at": now,
            })
        except Exception:
            continue
    return results


def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape (cookie-based Playwright)...")
    cookies = _load_cookies()
    if not cookies:
        return []

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print(f"[{SOURCE}] Playwright not installed — skipping")
        return []

    now = _now_iso()
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            ctx.add_cookies(cookies)
            page = ctx.new_page()

            # Verify cookies are valid — a logged-in user should not land on /login
            print(f"[{SOURCE}] Verifying cookie auth...")
            try:
                page.goto("https://wellfound.com/", timeout=30000)
                page.wait_for_timeout(2000)
                if "login" in page.url or "sign_in" in page.url:
                    print(
                        f"[{SOURCE}] Cookies expired or invalid — "
                        "re-export from Chrome using Cookie-Editor extension"
                    )
                    browser.close()
                    return []
                print(f"[{SOURCE}] Cookie auth OK")
            except PWTimeout:
                print(f"[{SOURCE}] Timeout verifying auth — proceeding anyway")

            for role in SEARCH_ROLES:
                try:
                    import urllib.parse
                    encoded = urllib.parse.quote(role)
                    page.goto(
                        f"https://wellfound.com/jobs?role={encoded}&remote=true",
                        timeout=30000,
                    )
                    page.wait_for_timeout(3000)
                    # Scroll to trigger lazy loading
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, window.innerHeight)")
                        page.wait_for_timeout(1000)
                    items = _parse_html(page.content(), now)
                    print(f"[{SOURCE}] '{role}' → {len(items)} raw")
                    results.extend(items)
                except PWTimeout:
                    print(f"[{SOURCE}] Timeout on role '{role}'")
                except Exception as e:
                    print(f"[{SOURCE}] Error on role '{role}' — {e}")
                time.sleep(2)

            browser.close()
    except Exception as e:
        print(f"[{SOURCE}] Browser error — {e}")
        return []

    seen: set[str] = set()
    unique = []
    for j in results:
        if j["url"] and j["url"] not in seen:
            seen.add(j["url"])
            unique.append(j)

    print(f"[{SOURCE}] {len(unique)} unique jobs")
    return unique
