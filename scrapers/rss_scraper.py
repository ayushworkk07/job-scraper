from __future__ import annotations
import time
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

FEEDS = [
    {
        "source": "WWR",
        "url": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    },
    {
        "source": "WWR",
        "url": "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    },
    {
        "source": "WorkingNomads",
        "url": "https://www.workingnomads.com/feed?category=development",
    },
    {
        "source": "Jobicy",
        "url": "https://jobicy.com/?feed=job_feed&job_categories=dev",
    },
]

KEYWORDS = ["backend", "node", "nodejs", "node.js", "software engineer", "sde", "software development"]


def _matches(entry: dict) -> bool:
    text = " ".join([
        entry.get("title", ""),
        entry.get("summary", ""),
    ]).lower()
    return any(kw in text for kw in KEYWORDS)


def _parse_date(entry) -> str | None:
    # feedparser populates published_parsed (struct_time in UTC) or published (string)
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    if hasattr(entry, "published") and entry.published:
        try:
            return parsedate_to_datetime(entry.published).astimezone(timezone.utc).isoformat()
        except Exception:
            pass
    return None


def _extract_company(entry, source: str) -> str:
    # WWR puts "Company: Title" in the title
    if source == "WWR":
        title = entry.get("title", "")
        if ": " in title:
            return title.split(": ", 1)[0].strip()
    # Try author field
    return entry.get("author", "") or ""


def _clean_title(title: str, source: str) -> str:
    if source == "WWR" and ": " in title:
        return title.split(": ", 1)[1].strip()
    return title


def scrape() -> list[dict]:
    results = []
    seen_urls: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()

    for feed_cfg in FEEDS:
        source = feed_cfg["source"]
        url = feed_cfg["url"]
        print(f"[{source}] Fetching RSS: {url}")
        try:
            feed = feedparser.parse(url)
            entries = feed.entries
        except Exception as e:
            print(f"[{source}] WARNING: failed to parse feed — {e}")
            time.sleep(1)
            continue

        print(f"[{source}] {len(entries)} raw entries")
        for entry in entries:
            if not _matches(entry):
                continue
            link = entry.get("link", "")
            if not link or link in seen_urls:
                continue
            seen_urls.add(link)

            results.append({
                "title": _clean_title(entry.get("title", ""), source),
                "company": _extract_company(entry, source),
                "url": link,
                "salary": None,
                "location_type": "REMOTE",
                "source": source,
                "posted_at": _parse_date(entry),
                "scraped_at": now,
            })

        time.sleep(1)

    print(f"[RSS] {len(results)} total matched across all feeds")
    return results
