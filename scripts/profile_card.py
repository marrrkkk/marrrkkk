
import argparse
import json
import os
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from make_ascii import RAMP

ROOT = Path(__file__).resolve().parent.parent
USER = "marrrkkk"
JOINED = date(2021, 8, 9)

WIDTH = 62


PROFILE = [
    ("OS", "Windows 11, Ubuntu (WSL)"),
    ("Uptime", "{uptime}"),
    ("Location", "Philippines"),
    ("Stack", "React, Next.js, Supabase"),
    ("Tools", "VS Code, Cursor"),
    None,
    ("Languages", "TypeScript, JavaScript, Python, SQL"),
    None,
    ("Role", "Full-Stack Engineer"),
    ("AI.Models", "Opus, Astra, Muse Spark"),
    ("AI.Agents", "Claude Code, Codex, OpenCode"),
    ("GitHub", USER),
    ("- Contact", None),
    ("Email", "marklouie.dev@gmail.com"),
    ("LinkedIn", "in/mark-louie-alvarez-b90162257"),
    ("Twitter", "@marrrkkk__"),
    ("- GitHub Stats", None),
    "{stats_repos}",
    "{stats_commits}",
]

THEMES = {
    # Catppuccin Mocha / Latte. key=mauve, value=blue, dim=overlay.
    "dark": dict(bg="#1e1e2e", text="#cdd6f4", key="#cba6f7", value="#89b4fa",
                 dim="#6c7086", ascii="#cdd6f4", invert=False,
                 palette=["#45475a", "#f38ba8", "#a6e3a1", "#f9e2af",
                          "#89b4fa", "#cba6f7", "#94e2d5", "#bac2de",
                          "#585b70", "#f5c2e7", "#94e2d5", "#fab387",
                          "#89dceb", "#f5e0dc", "#b4befe", "#cdd6f4"]),
    "light": dict(bg="#eff1f5", text="#4c4f69", key="#8839ef", value="#1e66f5",
                  dim="#9ca0b0", ascii="#4c4f69", invert=True,
                  palette=["#4c4f69", "#d20f39", "#40a02b", "#df8e1d",
                           "#1e66f5", "#8839ef", "#179299", "#dce0e8",
                           "#6c6f85", "#ea76cb", "#179299", "#fe640b",
                           "#04a5e5", "#dc8a78", "#7287fd", "#ffffff"]),
}

PAD = 28
ASCII_FONT, ASCII_CHAR_W, ASCII_LINE = 9, 5.4, 10.4
INFO_FONT, INFO_CHAR_W, INFO_LINE = 14, 8.4, 18.5
GAP = 28
PAL_W, PAL_H, PAL_GAP, PAL_TOP = 24, 14, 0, 12  # neofetch colour blocks


QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, first: 100) {
      totalCount
      nodes { stargazerCount }
    }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) {
      totalCount
    }
  }
}
"""

COMMITS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""


def graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_stats(token: str) -> dict:
    user = graphql(token, QUERY, {"login": USER})["user"]
    commits = 0
    now = datetime.now(timezone.utc)
    for year in range(JOINED.year, now.year + 1):
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = min(datetime(year + 1, 1, 1, tzinfo=timezone.utc), now)
        cc = graphql(token, COMMITS_QUERY, {
            "login": USER, "from": start.isoformat(), "to": end.isoformat(),
        })["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
    return {
        "repos": user["repositories"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in user["repositories"]["nodes"]),
        "commits": commits,
        "followers": user["followers"]["totalCount"],
    }


def uptime(today: date) -> str:
    months = (today.year - JOINED.year) * 12 + today.month - JOINED.month
    if today.day < JOINED.day:
        months -= 1
    anchor_month = JOINED.month - 1 + months
    anchor = date(JOINED.year + anchor_month // 12, anchor_month % 12 + 1, JOINED.day)
    days = (today - anchor).days
    years, months = divmod(months, 12)

    def unit(n, word):
        return f"{n} {word}{'' if n == 1 else 's'}"

    return f"{unit(years, 'year')}, {unit(months, 'month')}, {unit(days, 'day')}"

def kv(key: str, value: str, width: int) -> list[tuple[str, str]]:
    """'. Key: ...... value' padded to `width` characters."""
    head, tail = f"{key}:", f" {value}"
    dots = width - 2 - len(head) - len(tail) - 1
    if dots < 2:
        raise ValueError(f"line too long for {width} cols: {key}: {value}")
    return [("dim", ". "), ("key", key), ("text", ":"), ("dim", " " + "." * dots), ("value", tail)]


def rule(title: str, width: int) -> list[tuple[str, str]]:
    return [("text", title + " "), ("dim", "—" * (width - len(title) - 1))]


STAT_SPLIT = 36  


def stat_pair(left: tuple[str, str], right: tuple[str, str], width: int) -> list[tuple[str, str]]:
    """Two key/values on one line split by ' | ', like the sample's stats rows."""
    right_spans = kv(*right, width - STAT_SPLIT - 3 + 2)[1:] 
    return kv(*left, STAT_SPLIT) + [("text", " | ")] + right_spans


def info_lines(stats: dict, today: date) -> list[list[tuple[str, str]]]:
    lines = [rule("mark@marrrkkk", WIDTH)]
    for row in PROFILE:
        if row is None:
            lines.append([("dim", ".")])
        elif row == "{stats_repos}":
            lines.append(stat_pair(("Repos", f"{stats['repos']} {{Contributed: {stats['contributed']}}}"),
                                   ("Stars", f"{stats['stars']:,}"), WIDTH))
        elif row == "{stats_commits}":
            lines.append(stat_pair(("Commits", f"{stats['commits']:,}"),
                                   ("Followers", f"{stats['followers']:,}"), WIDTH))
        elif row[1] is None:
            lines.append(rule(row[0], WIDTH))
        else:
            key, value = row
            lines.append(kv(key, value.format(uptime=uptime(today)), WIDTH))
    return lines


def invert_ascii(line: str) -> str:
    last = len(RAMP) - 1
    return "".join(RAMP[last + 1 - RAMP.index(ch)] if ch in RAMP[1:] else ch for ch in line)


def render(theme: dict, portrait: list[str], info: list[list[tuple[str, str]]]) -> str:
    ascii_cols = max(len(l) for l in portrait)
    ascii_w = ascii_cols * ASCII_CHAR_W
    ascii_h = len(portrait) * ASCII_LINE
    info_w = WIDTH * INFO_CHAR_W
    info_h = len(info) * INFO_LINE
    palette_h = PAL_TOP + PAL_H
    content_h = max(ascii_h, info_h + palette_h)
    width = round(PAD * 2 + ascii_w + GAP + info_w)
    height = round(PAD * 2 + content_h)

    colours = {k: theme[k] for k in ("text", "key", "value", "dim")}
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Consolas, \'Courier New\', monospace">',
        "<style>text { white-space: pre; }</style>",
        f'<rect width="{width}" height="{height}" rx="15" fill="{theme["bg"]}"/>',
    ]

    y0 = PAD + (content_h - ascii_h) / 2 + ASCII_LINE * 0.8
    out.append(f'<g fill="{theme["ascii"]}" font-size="{ASCII_FONT}">')
    for i, line in enumerate(portrait):
        line = line.ljust(ascii_cols)
        if theme["invert"]:
            line = invert_ascii(line)
        out.append(
            f'<text x="{PAD}" y="{y0 + i * ASCII_LINE:.1f}" textLength="{ascii_w:.1f}" '
            f'lengthAdjust="spacing">{escape(line)}</text>'
        )
    out.append("</g>")

    x = PAD + ascii_w + GAP
    y1 = PAD + (content_h - (info_h + palette_h)) / 2 + INFO_LINE * 0.8
    out.append(f'<g font-size="{INFO_FONT}">')
    for i, spans in enumerate(info):
        n = sum(len(t) for _, t in spans)
        tspans = "".join(f'<tspan fill="{colours[s]}">{escape(t)}</tspan>' for s, t in spans)
        out.append(
            f'<text x="{x:.1f}" y="{y1 + i * INFO_LINE:.1f}" textLength="{n * INFO_CHAR_W:.1f}" '
            f'lengthAdjust="spacing">{tspans}</text>'
        )
    out.append("</g>")
    # neofetch-style palette: one row of 8 blocks under the details
    py = y1 + len(info) * INFO_LINE + PAL_TOP - PAL_H
    out.append("<g>")
    for c in range(8):
        bx = x + 2 * INFO_CHAR_W + c * (PAL_W + PAL_GAP)
        out.append(f'<rect x="{bx:.1f}" y="{py:.1f}" width="{PAL_W}" height="{PAL_H}" '
                   f'fill="{theme["palette"][c]}"/>')
    out.append("</g></svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use placeholder stats")
    args = ap.parse_args()

    if args.offline:
        stats = dict(repos=42, contributed=4, stars=12, commits=1234, followers=33)
    else:
        token = os.environ.get("ACCESS_TOKEN") or os.environ["GITHUB_TOKEN"]
        stats = fetch_stats(token)
    print("stats:", stats)

    portrait = (ROOT / "assets" / "portrait.txt").read_text(encoding="utf-8").splitlines()
    info = info_lines(stats, date.today())
    for name, theme in THEMES.items():
        path = ROOT / f"{name}_mode.svg"
        path.write_text(render(theme, portrait, info), encoding="utf-8")
        print("wrote", path.name)


if __name__ == "__main__":
    main()
