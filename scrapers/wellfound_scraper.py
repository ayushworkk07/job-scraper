from __future__ import annotations
"""
Wellfound scraper — cookie-based Playwright, GraphQL API interception.

The Wellfound SPA fetches jobs via internal GraphQL. We:
  1. Inject cookies so the session is authenticated
  2. Navigate to the jobs page and intercept XHR/fetch responses
  3. Pull job data from the GraphQL payload directly (avoids HTML selector fragility)
  4. Fall back to broad HTML scraping if interception yields nothing

Setup (one-time):
  Export cookies from Chrome using Cookie-Editor extension → JSON format.
  macOS:  base64 -i wellfound_cookies.json | pbcopy   → paste as WELLFOUND_COOKIES secret
  Linux:  base64 -w 0 wellfound_cookies.json

When cookies expire you'll see:
  [Wellfound] Cookies expired or invalid — re-export from Chrome using Cookie-Editor
"""
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone

SOURCE = "Wellfound"
COOKIES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wellfound_cookies.json")
SEARCH_ROLES = ["backend engineer", "software engineer", "node.js"]


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
    if not os.path.exists(COOKIES_FILE):
        print(f"[{SOURCE}] wellfound_cookies.json not found — skipping")
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
        if not cookies:
            print(f"[{SOURCE}] wellfound_cookies.json is empty — skipping")
            return None
        return cookies
    except Exception as e:
        print(f"[{SOURCE}] Failed to load cookies — {e}")
        return None


def _extract_from_graphql(payload: dict, now: str) -> list[dict]:
    """Pull jobs out of Wellfound's GraphQL response structure."""
    results = []
    raw_str = json.dumps(payload)

    # Walk all nested dicts/lists looking for job node patterns
    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            # Job node heuristic: has title + slug or url
            title = node.get("title") or node.get("jobTitle") or node.get("name")
            slug = node.get("slug") or node.get("jobListingSlug")
            remote = node.get("remote") or node.get("isRemote")
            company = node.get("company") or node.get("startup") or {}
            company_name = ""
            if isinstance(company, dict):
                company_name = company.get("name") or company.get("companyName") or ""

            if title and slug:
                url = f"https://wellfound.com/jobs/{slug}"
                compensation = node.get("compensation") or node.get("salary") or ""
                if isinstance(compensation, dict):
                    lo = compensation.get("min") or compensation.get("minValue")
                    hi = compensation.get("max") or compensation.get("maxValue")
                    curr = compensation.get("currency", "USD")
                    compensation = f"{curr} {lo:,}–{hi:,}" if lo and hi else None

                created = node.get("createdAt") or node.get("liveStartAt") or node.get("publishedAt")
                posted_at = None
                if created:
                    try:
                        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                        posted_at = dt.astimezone(timezone.utc).isoformat()
                    except Exception:
                        pass

                results.append({
                    "title": title,
                    "company": company_name,
                    "url": url,
                    "salary": compensation if isinstance(compensation, str) else None,
                    "location_type": "REMOTE" if remote else "INDIA",
                    "source": SOURCE,
                    "posted_at": posted_at,
                    "scraped_at": now,
                })
            else:
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        walk(v)

    walk(payload)
    return results


def _parse_html_broad(html: str, now: str) -> list[dict]:
    """Broad HTML fallback — grab any job-looking links from the rendered page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Try structured card selectors first
    for sel in [
        "div[data-test='JobListing']",
        "div[class*='JobCard']",
        "div[class*='job-card']",
        "div[class*='jobListing']",
        "div[class*='listing']",
        "[data-cy*='job']",
    ]:
        cards = soup.select(sel)
        if cards:
            for card in cards:
                a = card.select_one("a[href]")
                if not a:
                    continue
                href = a.get("href", "")
                url = f"https://wellfound.com{href}" if href.startswith("/") else href
                title_el = card.select_one("h2, h3, h4, [class*='title'], [class*='role']")
                title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                if url and title:
                    results.append({
                        "title": title, "company": "", "url": url,
                        "salary": None, "location_type": "REMOTE",
                        "source": SOURCE, "posted_at": None, "scraped_at": now,
                    })
            if results:
                return results

    # Absolute fallback: any /jobs/ link with reasonable text
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
                "source": SOURCE, "posted_at": None, "scraped_at": now,
            })

    return results


def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape (cookie-based Playwright + GraphQL interception)...")
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
    intercepted_jobs: list[dict] = []

    def handle_response(response):
        """Intercept GraphQL / JSON API responses and extract jobs."""
        try:
            url = response.url
            ct = response.headers.get("content-type", "")
            if response.status != 200:
                return
            if not ("json" in ct or "graphql" in url):
                return
            body = response.json()
            found = _extract_from_graphql(body, now)
            if found:
                intercepted_jobs.extend(found)
        except Exception:
            pass

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
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.on("response", handle_response)

            # Verify session
            print(f"[{SOURCE}] Verifying cookie auth...")
            try:
                page.goto("https://wellfound.com/", timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                if "login" in page.url or "sign_in" in page.url:
                    print(
                        f"[{SOURCE}] Cookies expired or invalid — "
                        "re-export from Chrome using Cookie-Editor extension"
                    )
                    browser.close()
                    return []
                print(f"[{SOURCE}] Cookie auth OK (page: {page.title()!r})")
            except PWTimeout:
                print(f"[{SOURCE}] Timeout on auth check — proceeding")

            for role in SEARCH_ROLES:
                try:
                    encoded = urllib.parse.quote(role)
                    target = f"https://wellfound.com/jobs?role={encoded}&remote=true"
                    print(f"[{SOURCE}] Navigating to: {target}")
                    page.goto(target, timeout=30000, wait_until="networkidle")
                    page.wait_for_timeout(2000)

                    # Scroll to trigger lazy-loaded cards
                    for _ in range(4):
                        page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
                        page.wait_for_timeout(800)

                    # Try waiting for job card elements
                    for sel in ["[data-test='JobListing']", "[class*='JobCard']", "a[href*='/jobs/']"]:
                        try:
                            page.wait_for_selector(sel, timeout=5000)
                            break
                        except PWTimeout:
                            continue

                    html_items = _parse_html_broad(page.content(), now)
                    print(f"[{SOURCE}] '{role}' → {len(html_items)} from HTML, {len(intercepted_jobs)} intercepted so far")
                    results.extend(html_items)
                except PWTimeout:
                    print(f"[{SOURCE}] Timeout on role '{role}'")
                except Exception as e:
                    print(f"[{SOURCE}] Error on role '{role}' — {e}")
                time.sleep(2)

            browser.close()
    except Exception as e:
        print(f"[{SOURCE}] Browser error — {e}")
        return []

    # Merge HTML results + intercepted GraphQL jobs, deduplicate
    all_jobs = intercepted_jobs + results
    seen: set[str] = set()
    unique = []
    for j in all_jobs:
        if j["url"] and j["url"] not in seen:
            seen.add(j["url"])
            unique.append(j)

    print(f"[{SOURCE}] {len(intercepted_jobs)} from GraphQL, {len(results)} from HTML → {len(unique)} unique")
    return unique
