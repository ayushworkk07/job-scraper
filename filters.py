from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

KEYWORDS = [
    "backend", "node", "nodejs", "node.js", "software engineer", "sde",
    "software development engineer", "backend engineer", "backend developer",
]

EXCLUDE_TITLE_KEYWORDS = [
    "senior", "lead", "principal", "staff", "manager", "director",
    "architect", "intern", "internship", "fresher", "10+", "8+", "7+", "6+",
]

EXPERIENCE_RE = re.compile(
    r'(\d+)\s*[-–to]+\s*(\d+)\s*(?:years?|yrs?)',
    re.IGNORECASE
)

MAX_HOURS_OLD = 48


def _title_matches_keywords(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in KEYWORDS)


def _title_excluded(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in EXCLUDE_TITLE_KEYWORDS)


def _experience_ok(text: str | None) -> bool:
    """Return True if experience range is 0-3 yrs, or if not detectable."""
    if not text:
        return True
    for m in EXPERIENCE_RE.finditer(text):
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > 3:
            return False
        if hi > 5:
            return False
    return True


def _is_recent(posted_at: str | None) -> bool:
    if not posted_at:
        return True
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - dt
        return age <= timedelta(hours=MAX_HOURS_OLD)
    except Exception:
        return True


def _location_ok(job: dict) -> bool:
    loc = (job.get("location") or "").lower()
    loc_type = (job.get("location_type") or "").upper()
    if loc_type in ("INDIA", "REMOTE"):
        return True
    remote_words = ("remote", "worldwide", "anywhere", "global")
    india_words = ("india", "bengaluru", "bangalore", "mumbai", "delhi",
                   "hyderabad", "pune", "gurgaon", "noida", "remote")
    return any(w in loc for w in remote_words + india_words)


def apply_filters(jobs: list[dict]) -> list[dict]:
    passed = []
    for job in jobs:
        title = job.get("title", "")
        if not _title_matches_keywords(title):
            continue
        if _title_excluded(title):
            continue
        desc = job.get("description", "")
        if not _experience_ok(desc):
            continue
        if not _is_recent(job.get("posted_at")):
            continue
        if not _location_ok(job):
            continue
        passed.append(job)
    return passed
