from __future__ import annotations
import json
import os

SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_jobs.json")


def load_seen() -> set:
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE) as f:
            data = json.load(f)
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def deduplicate(jobs: list[dict], seen: set) -> tuple[list[dict], set]:
    new_jobs = []
    new_urls = set()
    for job in jobs:
        url = job.get("url", "").strip()
        if not url or url in seen or url in new_urls:
            continue
        new_jobs.append(job)
        new_urls.add(url)
    return new_jobs, new_urls
