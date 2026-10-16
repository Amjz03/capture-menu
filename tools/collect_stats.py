"""Adds today's numbers to stats/history.json: downloads of every release file (all time, as GitHub
counts them, anonymous downloads included) and, with a token that may read traffic, page views, unique
visitors, clones, referrers and popular pages. GitHub keeps traffic for 14 days only, so running this
daily keeps the history.

    python tools/collect_stats.py <history.json> [owner/repo]

GH_TOKEN (or GITHUB_TOKEN) is used for downloads; TRAFFIC_TOKEN, when set, also for traffic.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
repo = sys.argv[2] if len(sys.argv) > 2 else "Amjz03/capture-menu"
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get(url: str, token: str | None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "capture-menu-stats"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(f"https://api.github.com/{url}", headers=headers), timeout=30) as r:
        return json.load(r)


history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
for key in ("downloads", "views", "clones", "referrers", "paths"):
    history.setdefault(key, {})

# downloads: a snapshot of every file's all-time count; the change between days is that day's downloads
token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
releases, page = [], 1
while True:
    batch = get(f"repos/{repo}/releases?per_page=100&page={page}", token)
    releases += batch
    if len(batch) < 100:
        break
    page += 1
by_release = {r["tag_name"]: {a["name"]: a["download_count"] for a in r.get("assets", [])} for r in releases}
history["downloads"][today] = {
    "total": sum(sum(files.values()) for files in by_release.values()),
    "setup_exe": sum(files.get("CaptureMenu-Setup.exe", 0) for files in by_release.values()),
    "by_release": by_release,
}

# traffic: the last 14 days, re-read every day (GitHub fills in recent days late, so the newest value wins)
traffic = os.environ.get("TRAFFIC_TOKEN")
if traffic:
    for kind in ("views", "clones"):
        data = get(f"repos/{repo}/traffic/{kind}", traffic)
        for day in data.get(kind, []):
            history[kind][day["timestamp"][:10]] = {"count": day["count"], "uniques": day["uniques"]}
    history["referrers"][today] = get(f"repos/{repo}/traffic/popular/referrers", traffic)
    history["paths"][today] = [{k: p[k] for k in ("path", "title", "count", "uniques")}
                               for p in get(f"repos/{repo}/traffic/popular/paths", traffic)]
else:
    print("TRAFFIC_TOKEN not set: downloads only")

meta = get(f"repos/{repo}", token)
history["repo"] = {"stars": meta["stargazers_count"], "watchers": meta["subscribers_count"],
                   "forks": meta["forks_count"]}
history["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(history, indent=1, sort_keys=True), encoding="utf-8")
print(f"{today}: {history['downloads'][today]['total']} downloads in total, traffic {'saved' if traffic else 'skipped'}")
