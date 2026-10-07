"""Shared bits for the profile cards: calendar fetch, dither patterns,
pixel sprites and the SMIL timeline. (Split out of pacman_grid.py.)"""
import re
import urllib.request
from datetime import date
from zoneinfo import ZoneInfo

from profile_card import USER

TZ = ZoneInfo("Asia/Manila")

PX = 2

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def day(d: date, count: int, level: int) -> dict:
    return {"date": d, "weekday": (d.weekday() + 1) % 7, "count": count, "level": level}


def to_weeks(days: list[dict]) -> list[list[dict]]:
    """Group days into Sunday-first columns, like the GitHub calendar."""
    weeks: list[list[dict]] = []
    for d in sorted(days, key=lambda d: d["date"]):
        if not weeks or d["weekday"] == 0:
            weeks.append([])
        weeks[-1].append(d)
    return weeks


def fetch_public_calendar() -> list[list[dict]]:
    """The calendar on github.com/<user>: what visitors see, no token needed."""
    req = urllib.request.Request(f"https://github.com/users/{USER}/contributions",
                                 headers={"User-Agent": "profile-readme"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8")
    cells = re.findall(r'data-date="([\d-]+)" id="(contribution-day-component-[\d-]+)" data-level="(\d)"', html)
    tips = dict(re.findall(r'for="(contribution-day-component-[\d-]+)"[^>]*>([^<]*)</tool-tip>', html))
    if len(cells) < 300:
        raise RuntimeError(f"contributions page changed: parsed {len(cells)} days")
    days = []
    for iso, cid, level in cells:
        m = re.match(r"(\d+) contribution", tips.get(cid, ""))
        days.append(day(date.fromisoformat(iso), int(m.group(1)) if m else 0, int(level)))
    return to_weeks(days)


def pixel_art(rows: list[str], fill: str, px: int = PX) -> str:
    """Centre a '#' bitmap on (0, 0) as crisp squares."""
    off = len(rows) * px / 2
    return "".join(
        f'<rect x="{x * px - off}" y="{y * px - off}" width="{px}" height="{px}"/>'
        for y, row in enumerate(rows) for x, ch in enumerate(row) if ch == "#"
    ).join([f'<g fill="{fill}">', "</g>"])


def patterns(ink: str) -> str:
    """Level 0-3 dither fills: 4x4 tiles of 2px 'pixels' (level 0 is a faint 1px dot)."""
    def pat(pid, rects, opacity=1):
        body = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{w}"/>' for x, y, w in rects)
        return (f'<pattern id="{pid}" width="4" height="4" patternUnits="userSpaceOnUse">'
                f'<g fill="{ink}" opacity="{opacity}">{body}</g></pattern>')
    return "".join([
        pat("l0", [(0, 0, 1)], 0.45),
        pat("l1", [(0, 0, 2)]),
        pat("l2", [(0, 0, 2), (2, 2, 2)]),
        pat("l3", [(0, 0, 2), (2, 2, 2), (2, 0, 2)]),
    ])


class Timeline:
    """Builds SMIL attributes on one shared loop of `dur` seconds."""

    def __init__(self, dur: float):
        self.dur = dur
        self.loop = f'dur="{dur:.2f}s" repeatCount="indefinite"'

    def key(self, t: float) -> str:
        return f"{min(max(t / self.dur, 0), 1):.5f}"

    def steps(self, changes: list[tuple[float, str]]) -> str:
        """Discrete values from (time, value) change points; first must be at 0."""
        pts = []
        for t, v in changes:
            if pts and pts[-1][1] == v:
                continue
            if pts and self.key(t) == self.key(pts[-1][0]):
                pts[-1] = (pts[-1][0], v)
            else:
                pts.append((t, v))
        return (f'values="{";".join(v for _, v in pts)}" '
                f'keyTimes="{";".join(self.key(t) for t, _ in pts)}" calcMode="discrete" {self.loop}')

    def show(self, changes: list[tuple[float, bool]]) -> str:
        return f'<animate attributeName="opacity" {self.steps([(t, "1" if on else "0") for t, on in changes])}/>'

    def motion(self, times: list[float], points: list[tuple[float, float]]) -> str:
        times, points = [0.0] + times + [self.dur], [points[0]] + points + [points[-1]]
        keep = [0] + [i for i in range(1, len(times)) if self.key(times[i]) != self.key(times[i - 1])]
        vals = ";".join(f"{points[i][0]},{points[i][1]}" for i in keep)
        keys = ";".join(self.key(times[i]) for i in keep)
        return f'<animateMotion values="{vals}" keyTimes="{keys}" calcMode="linear" {self.loop}/>'
