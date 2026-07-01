from __future__ import annotations
"""
Wellfound scraper — two strategies:

1. Direct GraphQL API (requests, no browser) with session cookie.
   Wellfound's SPA uses /graphql internally. DataDome targets browser
   fingerprints; direct API calls with the auth cookie often bypass it.

2. Cookie-based Playwright fallback if GraphQL returns nothing.

Setup (one-time):
  Export cookies from Chrome using Cookie-Editor extension → JSON format.
  macOS:  base64 -i wellfound_cookies.json | pbcopy  → WELLFOUND_COOKIES secret
  Linux:  base64 -w 0 wellfound_cookies.json

Cookie expiry warning:
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
GRAPHQL_URL = "https://wellfound.com/graphql"
SEARCH_ROLES = ["backend engineer", "software engineer", "node.js"]

# GraphQL query used by the Wellfound SPA for job listings
JOBS_QUERY = """
query JobSearchResults($query: String, $remote: Boolean, $page: Int) {
  jobListings(query: $query, remote: $remote, page: $page) {
    total
    jobListings {
      id
      title
      slug
      liveStartAt
      compensation
      remote
      locationNames
      jobType
      startup {
        name
        slug
      }
    }
  }
}
"""


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
        if not raw:
            print(f"[{SOURCE}] wellfound_cookies.json is empty — skipping")
            return None
        return raw
    except Exception as e:
        print(f"[{SOURCE}] Failed to load cookies — {e}")
        return None


def _cookies_as_header(cookies: list[dict]) -> str:
    """Convert Cookie-Editor JSON to a Cookie: header string."""
    parts = []
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name and value:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def _cookies_for_playwright(cookies: list[dict]) -> list[dict]:
    """Convert Cookie-Editor JSON to Playwright cookie format."""
    result = []
    for c in cookies:
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
        result.append(entry)
    return result


def _parse_graphql_response(data: dict, now: str) -> list[dict]:
    results = []
    try:
        listings = (
            data.get("data", {})
                .get("jobListings", {})
                .get("jobListings", [])
        )
        for j in listings:
            slug = j.get("slug", "")
            title = j.get("title", "")
            startup = j.get("startup") or {}
            company = startup.get("name", "") if isinstance(startup, dict) else ""
            url = f"https://wellfound.com/jobs/{slug}" if slug else ""
            if not url or not title:
                continue

            comp = j.get("compensation")
            salary = None
            if isinstance(comp, str) and comp:
                salary = comp
            elif isinstance(comp, dict):
                lo = comp.get("min")
                hi = comp.get("max")
                curr = comp.get("currency", "USD")
                if lo and hi:
                    salary = f"{curr} {lo:,}–{hi:,}"

            live = j.get("liveStartAt")
            posted_at = None
            if live:
                try:
                    dt = datetime.fromisoformat(str(live).replace("Z", "+00:00"))
                    posted_at = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

            results.append({
                "title": title,
                "company": company,
                "url": url,
                "salary": salary,
                "location_type": "REMOTE" if j.get("remote") else "INDIA",
                "source": SOURCE,
                "posted_at": posted_at,
                "scraped_at": now,
            })
    except Exception as e:
        print(f"[{SOURCE}] GraphQL parse error — {e}")
    return results


# ── Strategy 1: Direct GraphQL API ────────────────────────────────────────────

def _scrape_graphql(cookies: list[dict], now: str) -> list[dict]:
    import requests

    cookie_header = _cookies_as_header(cookies)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cookie": cookie_header,
        "Referer": "https://wellfound.com/jobs",
        "Origin": "https://wellfound.com",
        "X-Requested-With": "XMLHttpRequest",
    }

    results = []
    seen: set[str] = set()

    for role in SEARCH_ROLES:
        try:
            payload = {
                "query": JOBS_QUERY,
                "variables": {"query": role, "remote": True, "page": 1},
            }
            r = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=20)
            if r.status_code == 401 or r.status_code == 403:
                print(f"[{SOURCE}] GraphQL {r.status_code} — cookies may be expired")
                return []
            if r.status_code != 200:
                print(f"[{SOURCE}] GraphQL {r.status_code} for '{role}' — skipping")
                time.sleep(1)
                continue

            ct = r.headers.get("content-type", "")
            if "json" not in ct:
                print(f"[{SOURCE}] GraphQL returned non-JSON for '{role}' (got {ct[:40]}) — likely blocked")
                time.sleep(1)
                continue

            data = r.json()
            if "errors" in data:
                errs = data["errors"]
                msg = errs[0].get("message", "") if errs else ""
                if "auth" in msg.lower() or "login" in msg.lower():
                    print(f"[{SOURCE}] Cookies expired or invalid — re-export from Chrome using Cookie-Editor")
                    return []
                print(f"[{SOURCE}] GraphQL errors for '{role}': {msg}")

            items = _parse_graphql_response(data, now)
            print(f"[{SOURCE}] GraphQL '{role}' → {len(items)} jobs")
            for item in items:
                if item["url"] not in seen:
                    seen.add(item["url"])
                    results.append(item)

        except Exception as e:
            print(f"[{SOURCE}] GraphQL request failed for '{role}' — {e}")
        time.sleep(1)

    return results


# ── Strategy 2: Playwright fallback ───────────────────────────────────────────

def _parse_html_broad(html: str, now: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    results = []

    for sel in [
        "div[data-test='JobListing']", "div[class*='JobCard']",
        "div[class*='job-card']", "div[class*='jobListing']",
        "div[class*='listing']", "[data-cy*='job']",
    ]:
        cards = soup.select(sel)
        if cards:
            for card in cards:
                a = card.select_one("a[href]")
                if not a:
                    continue
                href = a.get("href", "")
                url = f"https://wellfound.com{href}" if href.startswith("/") else href
                title_el = card.select_one("h2,h3,h4,[class*='title'],[class*='role']")
                title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                if url and title:
                    results.append({
                        "title": title, "company": "", "url": url,
                        "salary": None, "location_type": "REMOTE",
                        "source": SOURCE, "posted_at": None, "scraped_at": now,
                    })
            if results:
                return results

    # Last resort: any /jobs/ link
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


def _scrape_playwright(cookies: list[dict], now: str) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print(f"[{SOURCE}] Playwright not installed")
        return []

    pw_cookies = _cookies_for_playwright(cookies)
    results = []
    intercepted: list[dict] = []

    def handle_response(response):
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            body = response.json()
            items = _parse_graphql_response(body, now)
            intercepted.extend(items)
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
            ctx.add_cookies(pw_cookies)
            page = ctx.new_page()
            page.on("response", handle_response)

            for role in SEARCH_ROLES:
                try:
                    encoded = urllib.parse.quote(role)
                    page.goto(
                        f"https://wellfound.com/jobs?role={encoded}&remote=true",
                        timeout=35000,
                        wait_until="networkidle",
                    )
                    page.wait_for_timeout(2000)
                    for _ in range(4):
                        page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
                        page.wait_for_timeout(700)
                    html_items = _parse_html_broad(page.content(), now)
                    print(f"[{SOURCE}] Playwright '{role}' → {len(html_items)} HTML, {len(intercepted)} intercepted")
                    results.extend(html_items)
                except PWTimeout:
                    print(f"[{SOURCE}] Playwright timeout on '{role}'")
                except Exception as e:
                    print(f"[{SOURCE}] Playwright error on '{role}' — {e}")
                time.sleep(2)

            browser.close()
    except Exception as e:
        print(f"[{SOURCE}] Playwright browser error — {e}")

    return intercepted + results


# ── Public entry point ────────────────────────────────────────────────────────

def scrape() -> list[dict]:
    print(f"[{SOURCE}] Starting scrape...")
    cookies = _load_cookies()
    if not cookies:
        return []

    now = _now_iso()

    # Try direct GraphQL first (no browser, bypasses DataDome browser fingerprint)
    print(f"[{SOURCE}] Trying direct GraphQL API...")
    results = _scrape_graphql(cookies, now)

    if not results:
        print(f"[{SOURCE}] GraphQL returned nothing — trying Playwright fallback")
        results = _scrape_playwright(cookies, now)

    # Deduplicate
    seen: set[str] = set()
    unique = []
    for j in results:
        if j["url"] and j["url"] not in seen:
            seen.add(j["url"])
            unique.append(j)

    print(f"[{SOURCE}] {len(unique)} unique jobs")
    return unique
