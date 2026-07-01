from __future__ import annotations
"""Playwright browser scraper for local runs — scrapes Cutshort (JS-rendered)."""
import time
import urllib.parse
from datetime import datetime, timezone

CUTSHORT_SOURCE = "Cutshort"
CUTSHORT_KEYWORDS = ["backend", "nodejs", "software engineer"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_cutshort_page(html: str, now: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Cutshort uses styled-components (hashed class names) — try card selectors first
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
        # Fallback: collect unique /job/ links, filter out button text
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


def scrape_local_browser() -> list[dict]:
    """Launch one Playwright browser, scrape Cutshort, close."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("[BrowserScraper] Playwright not installed — skipping")
        return []

    now = _now_iso()
    cutshort_jobs: list[dict] = []

    print("[BrowserScraper] Launching Playwright browser...")

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
            page = ctx.new_page()

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

    print(f"[BrowserScraper] Done — {len(cutshort_jobs)} Cutshort")
    return cutshort_jobs
