from __future__ import annotations
"""
Shared Playwright browser for local runs.
Launches ONE browser, scrapes Wellfound (cookie auth) then Cutshort
(no auth needed) in sequence, then closes. Avoids spinning up two browsers.
"""
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone

COOKIES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wellfound_cookies.json")

WELLFOUND_SOURCE = "Wellfound"
CUTSHORT_SOURCE = "Cutshort"

WELLFOUND_ROLES = ["backend engineer", "software engineer", "node.js"]
CUTSHORT_KEYWORDS = ["backend", "nodejs", "software engineer"]


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


def _load_wellfound_cookies() -> list[dict] | None:
    if not os.path.exists(COOKIES_FILE):
        print(f"[{WELLFOUND_SOURCE}] wellfound_cookies.json not found — skipping Wellfound")
        return None
    try:
        with open(COOKIES_FILE) as f:
            raw = json.load(f)
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
            exp = c.get("expirationDate") or c.get("expires")
            if exp and isinstance(exp, (int, float)) and exp > 0:
                entry["expires"] = int(exp)
            cookies.append(entry)
        return cookies or None
    except Exception as e:
        print(f"[{WELLFOUND_SOURCE}] Failed to load cookies — {e}")
        return None


# ── Wellfound HTML parser ──────────────────────────────────────────────────

def _parse_wellfound_page(html: str, now: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Try structured card selectors
    cards = None
    for sel in [
        "div[data-test='JobListing']",
        "div[class*='JobCard']",
        "div[class*='job-card']",
        "div[class*='jobListing']",
        "[data-cy*='job']",
    ]:
        found = soup.select(sel)
        if found:
            cards = found
            break

    if cards:
        for card in cards:
            try:
                a = card.select_one("a[href]")
                if not a:
                    continue
                href = a.get("href", "")
                url = f"https://wellfound.com{href}" if href.startswith("/") else href
                title_el = card.select_one("h2,h3,h4,[class*='title'],[class*='role']")
                title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                company_el = card.select_one("[class*='company'],[class*='startup'],h4")
                company = company_el.get_text(strip=True) if company_el else ""
                salary_el = card.select_one("[class*='salary'],[class*='compensation']")
                salary = salary_el.get_text(strip=True) if salary_el else None
                time_el = card.select_one("time,[class*='time'],[class*='date']")
                posted_raw = (time_el.get("datetime") or time_el.get_text(strip=True)) if time_el else None
                if url and title:
                    results.append({
                        "title": title, "company": company, "url": url,
                        "salary": salary, "location_type": "REMOTE",
                        "source": WELLFOUND_SOURCE,
                        "posted_at": _parse_posted(posted_raw), "scraped_at": now,
                    })
            except Exception:
                continue
    else:
        # Broad fallback: any /jobs/ link
        for a in soup.select("a[href*='/jobs/']"):
            href = a.get("href", "")
            if not href or href in ("/jobs", "/jobs/"):
                continue
            url = f"https://wellfound.com{href}" if href.startswith("/") else href
            text = a.get_text(strip=True)
            if text and len(text) > 5:
                results.append({
                    "title": text, "company": "", "url": url,
                    "salary": None, "location_type": "REMOTE",
                    "source": WELLFOUND_SOURCE, "posted_at": None, "scraped_at": now,
                })

    return results


# ── Cutshort HTML parser ───────────────────────────────────────────────────

def _parse_cutshort_page(html: str, now: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    results = []

    cards = None
    for sel in [
        "div[class*='job-card']", "div[class*='JobCard']",
        "li[class*='job']", "div[data-testid*='job']",
        "div[class*='card']",
    ]:
        found = soup.select(sel)
        if found:
            cards = found
            break

    if cards:
        for card in cards:
            try:
                title_el = card.select_one("h2,h3,[class*='title'],[class*='designation']")
                title = title_el.get_text(strip=True) if title_el else ""
                company_el = card.select_one("[class*='company'],[class*='org'],[class*='employer']")
                company = company_el.get_text(strip=True) if company_el else ""
                a_el = card if card.name == "a" else card.select_one("a[href]")
                href = a_el.get("href", "") if a_el else ""
                url = f"https://cutshort.io{href}" if href.startswith("/") else href
                salary_el = card.select_one("[class*='salary'],[class*='ctc'],[class*='lpa']")
                salary = salary_el.get_text(strip=True) if salary_el else None
                if url and title:
                    results.append({
                        "title": title, "company": company, "url": url,
                        "salary": salary, "location_type": "INDIA",
                        "source": CUTSHORT_SOURCE, "posted_at": None, "scraped_at": now,
                    })
            except Exception:
                continue
    else:
        _SKIP = {"apply now", "apply", "view job", "view", "see details", "read more"}
        seen_urls: set[str] = set()
        for a in soup.select("a[href*='/job/']"):
            href = a.get("href", "")
            url = f"https://cutshort.io{href}" if href.startswith("/") else href
            text = a.get_text(strip=True)
            if not text or len(text) < 6 or text.lower() in _SKIP:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                "title": text, "company": "", "url": url,
                "salary": None, "location_type": "INDIA",
                "source": CUTSHORT_SOURCE, "posted_at": None, "scraped_at": now,
            })

    return results


# ── Shared browser scrape ──────────────────────────────────────────────────

def scrape_local_browser() -> list[dict]:
    """Launch one Playwright browser, scrape Wellfound then Cutshort, close."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("[BrowserScraper] Playwright not installed — skipping")
        return []

    now = _now_iso()
    wellfound_cookies = _load_wellfound_cookies()
    wellfound_jobs: list[dict] = []
    cutshort_jobs: list[dict] = []

    print("[BrowserScraper] Launching shared Playwright browser...")

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
                viewport={"width": 1280, "height": 900},
            )

            if wellfound_cookies:
                ctx.add_cookies(wellfound_cookies)

            page = ctx.new_page()

            # ── Wellfound ──────────────────────────────────────────────────
            # DataDome blocks all headless browsers on the jobs search page.
            # Wellfound is skipped until a non-headless or API-based solution is found.
            print(f"[{WELLFOUND_SOURCE}] Skipping — DataDome blocks headless browsers on job search pages")

            # ── Cutshort (same browser, same IP session) ───────────────────
            seen_cs: set[str] = set()
            for kw in CUTSHORT_KEYWORDS:
                try:
                    page.goto(
                        f"https://cutshort.io/jobs?keyword={urllib.parse.quote(kw)}&type=full-time",
                        timeout=60000,
                        wait_until="domcontentloaded",
                    )
                    page.wait_for_timeout(4000)
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, window.innerHeight)")
                        page.wait_for_timeout(800)
                    items = _parse_cutshort_page(page.content(), now)
                    print(f"[{CUTSHORT_SOURCE}] '{kw}' → {len(items)} raw")
                    for item in items:
                        if item["url"] and item["url"] not in seen_cs:
                            seen_cs.add(item["url"])
                            cutshort_jobs.append(item)
                except PWTimeout:
                    print(f"[{CUTSHORT_SOURCE}] Timeout on '{kw}'")
                except Exception as e:
                    print(f"[{CUTSHORT_SOURCE}] Error on '{kw}' — {e}")
                time.sleep(2)

            print(f"[{CUTSHORT_SOURCE}] {len(cutshort_jobs)} unique jobs")
            browser.close()

    except Exception as e:
        print(f"[BrowserScraper] Browser error — {e}")
        return []

    all_jobs = wellfound_jobs + cutshort_jobs
    print(f"[BrowserScraper] Done — {len(cutshort_jobs)} Cutshort = {len(all_jobs)} total")
    return all_jobs
