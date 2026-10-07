"""Daily profile-card updater for Vercel Cron.

Renders the SVGs with the existing scripts/* generators and commits them
back to this repo through the GitHub git-database API (one commit, so the
history stays clean). Triggered by Vercel Cron; guarded by CRON_SECRET.

Env: GH_TOKEN (fine-grained PAT, Contents read+write on this repo),
     CRON_SECRET (random string, also set in the Vercel dashboard).
"""
import base64
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import activity as act  # noqa: E402
from scripts import contrib_graph as graph  # noqa: E402
from scripts import profile_card as card  # noqa: E402
from scripts.common import TZ  # noqa: E402

REPO = "marrrkkk/marrrkkk"
BRANCH = "main"
API = "https://api.github.com"


def gh(token, method, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path, method=method, data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "profile-readme"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
    if not raw.strip():
        raise RuntimeError(f"empty response from {method} {path}")
    return json.loads(raw)


def bump_versions(text):
    return re.sub(r"\?v=(\d+)", lambda m: f"?v={int(m.group(1)) + 1}", text)


def file_blob_b64(token, path):
    """Current blob: (sha, text) for a repo file, via the Contents API."""
    data = gh(token, "GET", f"/repos/{REPO}/contents/{path}?ref={BRANCH}")
    return data["sha"], base64.b64decode(data["content"]).decode("utf-8")


def run_update():
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN env var is missing")
    today = datetime.now(TZ).date()

    # 1. neofetch card (live GitHub stats need the token)
    portrait = (ROOT / "assets" / "portrait.txt").read_text(encoding="utf-8").splitlines()
    stats = card.fetch_stats(token)
    info = card.info_lines(stats, today)
    files = {
        "dark_mode.svg": card.render(card.THEMES["dark"], portrait, info),
        "light_mode.svg": card.render(card.THEMES["light"], portrait, info),
    }

    # 2. monthly bar graph (public calendar, no token)
    weeks = graph.fetch_public_calendar()
    days = graph.month_days(weeks, today)
    tiles = graph.stats(days, today)
    for name, theme in card.THEMES.items():
        files[f"graph_{name}.svg"] = graph.render(theme, days, tiles, today)

    # 3. activity timeline (public profile HTML, no token)
    y, m = today.year, today.month
    months = []
    for _ in range(act.MONTHS):
        months.append({"year": y, "month": m, "items": act.fetch_month(y, m)})
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    atiles = act.totals(months)
    for name, theme in card.THEMES.items():
        files[f"activity_{name}.svg"] = act.render(name, theme, months, atiles)

    # 4. README with fresh cache-busters
    _, readme = file_blob_b64(token, "README.md")
    readme_new = bump_versions(readme)
    if readme_new == readme:  # keep ?v= working even if someone edits URLs
        raise RuntimeError("no ?v= cache-busters found in README.md")

    # 5. single commit through the git-database API (skip when unchanged)
    ref = gh(token, "GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")
    base_commit = ref["object"]["sha"]
    base_tree = gh(token, "GET", f"/repos/{REPO}/git/commits/{base_commit}")["tree"]["sha"]
    tree = []
    for path, text in {**files, "README.md": readme_new}.items():
        blob = gh(token, "POST", f"/repos/{REPO}/git/blobs",
                  {"content": base64.b64encode(text.encode()).decode(), "encoding": "base64"})
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    new_tree = gh(token, "POST", f"/repos/{REPO}/git/trees",
                  {"base_tree": base_tree, "tree": tree})["sha"]
    if new_tree == base_tree:
        return {"ok": True, "changed": False, "stats": stats}
    commit = gh(token, "POST", f"/repos/{REPO}/git/commits",
                {"message": "chore: update profile cards",
                 "tree": new_tree, "parents": [base_commit]})["sha"]
    gh(token, "PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}", {"sha": commit})
    return {"ok": True, "changed": True, "commit": commit, "stats": stats}


class handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        secret = os.environ.get("CRON_SECRET")
        if not secret or self.headers.get("Authorization") != f"Bearer {secret}":
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            self._json(200, run_update())
        except Exception as err:  # noqa: BLE001 - surfaced in Vercel logs
            self._json(500, {"ok": False, "error": f"{type(err).__name__}: {err}"})

    def log_message(self, *args, **kwargs):  # quieter Vercel logs
        pass
