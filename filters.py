from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta

# Title must contain at least one of these
KEYWORDS = [
    "backend", "node", "nodejs", "node.js", "software engineer", "sde",
    "software development engineer", "backend engineer", "backend developer",
]

# Any of these in the title → skip
EXCLUDE_TITLE_KEYWORDS = [
    # Wrong seniority (above SDE-2)
    "senior", "sr.", "sr ", "lead ", "lead-", "principal", "staff",
    "manager", "director", "architect", "vp ", "vice president",
    "sde-3", "sde 3", "sde3", "sde-4", "sde 4", "sde iv",
    "engineer iii", "engineer iv", "developer iii", "developer iv",
    "level 3", "level 4", "smts", "lmts",
    # Wrong seniority (below SDE-1)
    "intern", "internship", "fresher", "trainee", "junior",
    # Wrong employment type
    "contract", "freelance",
    # Wrong tech stack
    "php", "devops", "sdet", "qa ",
    "frontend", "front-end", "front end",
    "android", "flutter", "react native", "ios ",
    "ui developer", "ui/ux", ".net developer",
    "data engineer", "ml engineer", "machine learning",
    # Experience mentioned in title
    "10+ years", "8+ years", "7+ years", "6+ years", "5+ years", "4+ years",
]

BLOCKED_COMPANIES = [
    # IT outsourcing / staffing
    "wipro", "infosys", "tcs", "tata consultancy", "cognizant", "hcl",
    "accenture", "capgemini", "tech mahindra", "mphasis", "ltimindtree",
    "hexaware", "mindtree", "niit", "mastech",
    # Job aggregators posting as employers
    "shine.com", "foundit", "naukri", "instahyre", "fetchjobs",
    "mercor", "braintrust", "talentgigs", "hackajob",
    "tekpillar", "smowcode", "erekrut", "hirist",
]

# For INDIA location_type: if a location string is set, it must contain one of these
INDIA_ALLOWED_CITIES = {
    "bangalore", "bengaluru", "gurugram", "gurgaon", "noida",
    "delhi", "new delhi", "pune", "mumbai", "bombay", "hyderabad",
    "india", "maharashtra", "remote",
}

# For INDIA: block if location string contains any of these
INDIA_BLOCKED_LOCATIONS = [
    "gujarat", "ahmedabad", "jaipur", "rajasthan", "surat", "vadodara",
    "indore", "bhopal", "nagpur", "coimbatore", "kochi", "punjab",
    "chennai", "kerala", "tamil nadu", "kolkata", "mohali", "chandigarh",
    "lucknow", "patna", "bhubaneswar", "dehradun",
]

# For REMOTE: block if location/URL contains any of these
REMOTE_BLOCKED_SIGNALS = [
    "us only", "usa only", "united states only", "north america only",
    "americas only", "uk only", "europe only", "australia only",
    "canada only", "eu only", "emea only",
    # Specific countries not relevant to user
    "bulgaria", "ukraine", "poland", "romania", "turkey",
    "pakistan", "latin america", "south america",
    "mexico", "brazil",
]

MAX_HOURS_INDIA = 48
MAX_HOURS_REMOTE = 7 * 24  # remote listings are valid for much longer


def _title_matches_keywords(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in KEYWORDS)


def _title_excluded(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in EXCLUDE_TITLE_KEYWORDS)


def _company_blocked(company: str) -> bool:
    if not company:
        return False
    c = company.lower()
    return any(b in c for b in BLOCKED_COMPANIES)


def _experience_ok(description: str | None) -> bool:
    """Return False if job clearly requires 4+ years. True if unknown/unclear."""
    if not description:
        return True
    t = description.lower()
    # "3-5 years" / "3 to 5 years"
    for m in re.finditer(r'(\d+)\s*[-–to]+\s*(\d+)\s*(?:years?|yrs?)', t):
        if int(m.group(1)) >= 4:
            return False
    # "4+ years of experience" / "4 years experience"
    for m in re.finditer(r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+)?(?:experience|exp\b)', t):
        if int(m.group(1)) >= 4:
            return False
    # "minimum 4 years" / "at least 4 years"
    for m in re.finditer(r'(?:minimum|min\.?\s*|at least\s+)(\d+)\s*(?:years?|yrs?)', t):
        if int(m.group(1)) >= 4:
            return False
    return True


def _is_recent(job: dict) -> bool:
    posted_at = job.get("posted_at")
    if not posted_at:
        return True
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - dt
        loc_type = (job.get("location_type") or "").upper()
        max_hours = MAX_HOURS_REMOTE if loc_type == "REMOTE" else MAX_HOURS_INDIA
        return age <= timedelta(hours=max_hours)
    except Exception:
        return True


def _location_ok(job: dict) -> bool:
    loc_type = (job.get("location_type") or "").upper()
    loc = (job.get("location") or "").lower()

    if loc_type == "REMOTE":
        # Check location field + URL for country restrictions
        check = loc + " " + (job.get("url") or "").lower()
        if any(s in check for s in REMOTE_BLOCKED_SIGNALS):
            return False
        return True

    if loc_type == "INDIA":
        if not loc:
            return True  # no city specified → could be anywhere in India, allow
        if any(b in loc for b in INDIA_BLOCKED_LOCATIONS):
            return False
        # Must be in an allowed city (or "india" / "remote" keyword present)
        if any(city in loc for city in INDIA_ALLOWED_CITIES):
            return True
        return False  # some other city not on our list

    # Unknown location_type — loose pass
    return True


def apply_filters(jobs: list[dict]) -> list[dict]:
    passed = []
    for job in jobs:
        title = job.get("title", "")
        if not _title_matches_keywords(title):
            continue
        if _title_excluded(title):
            continue
        if _company_blocked(job.get("company", "")):
            continue
        if not _experience_ok(job.get("description")):
            continue
        if not _is_recent(job):
            continue
        if not _location_ok(job):
            continue
        passed.append(job)
    return passed
