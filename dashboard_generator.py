from __future__ import annotations
"""Generate index.html from jobs.json — fully self-contained, no CDN."""
import json
import os
from datetime import datetime, timezone

JOBS_FILE = os.path.join(os.path.dirname(__file__), "jobs.json")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "index.html")

SOURCE_COLORS = {
    "Indeed": "#2164F3",
    "LinkedIn": "#0A66C2",
    "Wellfound": "#FB5F1C",
    "Cutshort": "#7B61FF",
    "RemoteOK": "#00D4AA",
    "Himalayas": "#3B82F6",
    "Remotive": "#16A34A",
    "WWR": "#DC2626",
    "WorkingNomads": "#D97706",
    "Jobicy": "#7C3AED",
    "YCombinator": "#FF6600",
}


def _time_ago(iso: str | None) -> str:
    if not iso:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        secs = int(diff.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return "Unknown"


def generate() -> None:
    if not os.path.exists(JOBS_FILE):
        print("[Dashboard] jobs.json not found — generating empty dashboard")
        jobs_data = {"last_updated": None, "total_count": 0, "jobs": []}
    else:
        with open(JOBS_FILE) as f:
            jobs_data = json.load(f)

    jobs = jobs_data.get("jobs", [])
    last_updated = jobs_data.get("last_updated")
    last_updated_ago = _time_ago(last_updated)

    all_sources = sorted(set(j.get("source", "") for j in jobs if j.get("source")))
    india_count = sum(1 for j in jobs if j.get("location_type") == "INDIA")
    remote_count = sum(1 for j in jobs if j.get("location_type") == "REMOTE")

    from datetime import date
    today_str = date.today().isoformat()
    today_count = sum(1 for j in jobs if (j.get("posted_at") or "").startswith(today_str))

    jobs_json_str = json.dumps(jobs, ensure_ascii=False)

    # Build source badge colors JS map
    badge_colors_js = json.dumps(SOURCE_COLORS)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Ayush's Job Radar</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0f0f0f;--card:#1a1a1a;--card-hover:#222;--border:#2a2a2a;
  --text:#e8e8e8;--muted:#888;--accent:#3b82f6;
  --india:#f97316;--remote:#3b82f6;
}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh}}
a{{color:inherit;text-decoration:none}}

/* Header */
.header{{background:#111;border-bottom:1px solid var(--border);padding:20px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}}
.header-title{{font-size:1.4rem;font-weight:700;letter-spacing:-0.5px}}
.header-title span{{color:var(--accent)}}
.header-meta{{font-size:.8rem;color:var(--muted)}}
.next-scan{{font-size:.8rem;color:var(--muted);background:#1e1e1e;border:1px solid var(--border);border-radius:6px;padding:4px 10px}}

/* Stats bar */
.stats{{display:flex;gap:0;border-bottom:1px solid var(--border);background:#111}}
.stat{{flex:1;padding:14px 20px;text-align:center;border-right:1px solid var(--border)}}
.stat:last-child{{border-right:none}}
.stat-num{{font-size:1.5rem;font-weight:700;color:var(--text)}}
.stat-label{{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:2px}}

/* Controls */
.controls{{padding:16px 20px;border-bottom:1px solid var(--border);background:#111;display:flex;flex-direction:column;gap:10px}}
.filter-row{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
.filter-btn{{padding:5px 12px;border-radius:20px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:.78rem;cursor:pointer;transition:.15s}}
.filter-btn:hover,.filter-btn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
.search-sort{{display:flex;gap:10px;align-items:center}}
.search-box{{flex:1;background:#1a1a1a;border:1px solid var(--border);border-radius:8px;padding:8px 14px;color:var(--text);font-size:.88rem;outline:none}}
.search-box:focus{{border-color:var(--accent)}}
.sort-btn{{padding:7px 14px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:.78rem;cursor:pointer;white-space:nowrap}}
.sort-btn.active{{background:#1e2a3a;border-color:var(--accent);color:var(--accent)}}

/* Counter */
.count-bar{{padding:8px 20px;font-size:.8rem;color:var(--muted);border-bottom:1px solid var(--border);background:#0f0f0f}}

/* Cards */
.cards{{padding:16px 20px;display:grid;gap:12px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;transition:.15s;position:relative}}
.card:hover{{background:var(--card-hover);border-color:#3a3a3a}}
.card.applied{{opacity:.4}}
.card-top{{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}}
.badge{{font-size:.68rem;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:.4px;text-transform:uppercase;color:#fff}}
.loc-badge{{font-size:.68rem;font-weight:600;padding:3px 8px;border-radius:4px;text-transform:uppercase}}
.badge-india{{background:var(--india)}}
.badge-remote{{background:var(--remote)}}
.card-title{{font-size:1rem;font-weight:600;margin-bottom:6px;line-height:1.3}}
.card-meta{{display:flex;align-items:center;gap:14px;font-size:.8rem;color:var(--muted);flex-wrap:wrap}}
.card-meta span{{display:flex;align-items:center;gap:4px}}
.card-actions{{position:absolute;right:14px;bottom:14px;display:flex;gap:8px}}
.btn-apply{{padding:5px 12px;border-radius:6px;border:none;background:var(--accent);color:#fff;font-size:.78rem;font-weight:600;cursor:pointer}}
.btn-apply:hover{{background:#2563eb}}
.btn-check{{padding:5px 10px;border-radius:6px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:.78rem;cursor:pointer;transition:.15s}}
.btn-check.done{{background:#166534;border-color:#16a34a;color:#4ade80}}

/* Empty state */
.empty{{padding:60px 20px;text-align:center;color:var(--muted)}}
.empty h3{{font-size:1.1rem;margin-bottom:8px}}
.clear-btn{{margin-top:14px;padding:8px 18px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--muted);cursor:pointer;font-size:.85rem}}
.clear-btn:hover{{border-color:var(--accent);color:var(--accent)}}

@media(max-width:600px){{
  .stats{{flex-wrap:wrap}}
  .stat{{min-width:50%;border-right:none;border-bottom:1px solid var(--border)}}
  .card-actions{{position:static;margin-top:12px;justify-content:flex-end}}
  .header{{flex-direction:column;align-items:flex-start}}
}}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="header-title">Ayush's <span>Job Radar</span></div>
    <div class="header-meta">Last updated: {last_updated_ago} &nbsp;·&nbsp; {len(jobs)} jobs in 7-day window</div>
  </div>
  <div class="next-scan" id="countdown">Next scan: calculating…</div>
</div>

<div class="stats">
  <div class="stat"><div class="stat-num">{len(jobs)}</div><div class="stat-label">Total (7d)</div></div>
  <div class="stat"><div class="stat-num">{today_count}</div><div class="stat-label">New Today</div></div>
  <div class="stat"><div class="stat-num">{india_count}</div><div class="stat-label">🇮🇳 India</div></div>
  <div class="stat"><div class="stat-num">{remote_count}</div><div class="stat-label">🌐 Remote</div></div>
</div>

<div class="controls">
  <div class="filter-row" id="source-tabs">
    <button class="filter-btn active" data-source="all">All</button>
    {"".join(f'<button class="filter-btn" data-source="{s}">{s}</button>' for s in all_sources)}
  </div>
  <div class="filter-row" id="loc-tabs">
    <button class="filter-btn active" data-loc="all">All Locations</button>
    <button class="filter-btn" data-loc="INDIA">🇮🇳 India</button>
    <button class="filter-btn" data-loc="REMOTE">🌐 Remote</button>
  </div>
  <div class="search-sort">
    <input class="search-box" id="search" type="text" placeholder="Search by company or title…"/>
    <button class="sort-btn active" id="sort-new" onclick="setSort('new')">Newest First</button>
    <button class="sort-btn" id="sort-old" onclick="setSort('old')">Oldest First</button>
  </div>
</div>

<div class="count-bar" id="count-bar">Loading…</div>
<div class="cards" id="cards"></div>

<script>
const JOBS = {jobs_json_str};
const BADGE_COLORS = {badge_colors_js};
const LAST_UPDATED = {json.dumps(last_updated)};

const NEXT_RUN_INTERVAL_MS = 4 * 60 * 60 * 1000; // 4 hours

let activeSource = 'all';
let activeLoc = 'all';
let sortDir = 'new';
let searchVal = '';

// Load applied state from localStorage
function getApplied() {{
  try {{ return JSON.parse(localStorage.getItem('applied') || '{{}}'); }}
  catch {{ return {{}}; }}
}}
function toggleApplied(url) {{
  const a = getApplied();
  a[url] = !a[url];
  localStorage.setItem('applied', JSON.stringify(a));
  render();
}}

// Source badge HTML
function sourceBadge(source) {{
  const color = BADGE_COLORS[source] || '#555';
  return `<span class="badge" style="background:${{color}}">${{source}}</span>`;
}}

function locBadge(locType) {{
  if (locType === 'INDIA') return '<span class="badge loc-badge badge-india">India</span>';
  return '<span class="badge loc-badge badge-remote">Remote</span>';
}}

function timeAgo(iso) {{
  if (!iso) return 'Unknown';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff/60) + 'm ago';
  if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
  return Math.floor(diff/86400) + 'd ago';
}}

function render() {{
  const applied = getApplied();
  let filtered = JOBS.filter(j => {{
    if (activeSource !== 'all' && j.source !== activeSource) return false;
    if (activeLoc !== 'all' && j.location_type !== activeLoc) return false;
    if (searchVal) {{
      const q = searchVal.toLowerCase();
      if (!j.title.toLowerCase().includes(q) && !j.company.toLowerCase().includes(q)) return false;
    }}
    return true;
  }});

  filtered.sort((a, b) => {{
    const ta = new Date(a.posted_at || 0).getTime();
    const tb = new Date(b.posted_at || 0).getTime();
    return sortDir === 'new' ? tb - ta : ta - tb;
  }});

  // Applied jobs go to bottom
  filtered.sort((a, b) => {{
    const aa = applied[a.url] ? 1 : 0;
    const ba = applied[b.url] ? 1 : 0;
    return aa - ba;
  }});

  document.getElementById('count-bar').textContent = `${{filtered.length}} job${{filtered.length !== 1 ? 's' : ''}} shown`;

  const container = document.getElementById('cards');
  if (!filtered.length) {{
    container.innerHTML = `<div class="empty">
      <h3>No jobs match your filters</h3>
      <p>Try adjusting the filters or wait for the next scan.</p>
      <button class="clear-btn" onclick="clearFilters()">Clear all filters</button>
    </div>`;
    return;
  }}

  container.innerHTML = filtered.map(j => {{
    const isApplied = !!applied[j.url];
    const checkClass = isApplied ? 'done' : '';
    const checkLabel = isApplied ? '✓ Applied' : '✓';
    return `<div class="card${{isApplied ? ' applied' : ''}}">
      <div class="card-top">
        ${{sourceBadge(j.source)}}
        ${{locBadge(j.location_type)}}
      </div>
      <div class="card-title">${{j.title || 'Untitled'}}</div>
      <div class="card-meta">
        <span>🏢 ${{j.company || 'Unknown'}}</span>
        ${{j.salary ? `<span>💰 ${{j.salary}}</span>` : ''}}
        <span>⏰ ${{timeAgo(j.posted_at)}}</span>
      </div>
      <div class="card-actions">
        <button class="btn-apply" onclick="window.open('${{j.url}}','_blank')">Apply ↗</button>
        <button class="btn-check ${{checkClass}}" onclick="toggleApplied('${{j.url}}')">${{checkLabel}}</button>
      </div>
    </div>`;
  }}).join('');
}}

function clearFilters() {{
  activeSource = 'all';
  activeLoc = 'all';
  searchVal = '';
  document.getElementById('search').value = '';
  document.querySelectorAll('#source-tabs .filter-btn').forEach((b,i) => b.classList.toggle('active', i===0));
  document.querySelectorAll('#loc-tabs .filter-btn').forEach((b,i) => b.classList.toggle('active', i===0));
  render();
}}

function setSort(dir) {{
  sortDir = dir;
  document.getElementById('sort-new').classList.toggle('active', dir==='new');
  document.getElementById('sort-old').classList.toggle('active', dir==='old');
  render();
}}

// Tab clicks
document.getElementById('source-tabs').addEventListener('click', e => {{
  if (!e.target.dataset.source) return;
  document.querySelectorAll('#source-tabs .filter-btn').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  activeSource = e.target.dataset.source;
  render();
}});
document.getElementById('loc-tabs').addEventListener('click', e => {{
  if (!e.target.dataset.loc) return;
  document.querySelectorAll('#loc-tabs .filter-btn').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  activeLoc = e.target.dataset.loc;
  render();
}});

document.getElementById('search').addEventListener('input', e => {{
  searchVal = e.target.value.trim();
  render();
}});

// Countdown to next 4-hour mark
function updateCountdown() {{
  if (!LAST_UPDATED) {{ document.getElementById('countdown').textContent = 'Next scan: unknown'; return; }}
  const last = new Date(LAST_UPDATED).getTime();
  const next = last + NEXT_RUN_INTERVAL_MS;
  const diff = next - Date.now();
  if (diff <= 0) {{ document.getElementById('countdown').textContent = 'Next scan: any moment'; return; }}
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  document.getElementById('countdown').textContent = `Next scan: ${{h}}h ${{m}}m ${{s}}s`;
}}
setInterval(updateCountdown, 1000);
updateCountdown();

render();
</script>
</body>
</html>"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Dashboard] Generated index.html ({len(jobs)} jobs)")
