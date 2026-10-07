"""Render the contribution graph for the current month: graph_dark.svg + graph_light.svg.

One bar per day of the current month, in the WakaTime-dashboard look of the
other cards: stat tiles with a dithered strip, bars shaded with 1-bit dither
levels (in orange) by how busy the day was, dotted guide lines, day numbers
along the bottom. A pixel arrow and "Today" mark today's bar; days still to
come are faint placeholders.
It rolls over to the new month on the 1st.

Data is the public contribution calendar (the same one the Pac-Man grid uses;
no token needed).

Usage:
    python scripts/contrib_graph.py
"""
import calendar
import sys
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from pacman_grid import TZ, fetch_public_calendar, patterns, pixel_art
from profile_card import PAD, THEMES

ROOT = Path(__file__).resolve().parent.parent
WIDTH = 900
TILE_H = 52
CHART_H = 170
AXIS_W = 30                # room for the y-axis numbers
BAR_GAP = 6
ARROW = ["..###..", "..###..", "..###..", "#######", ".#####.", "..###..", "...#..."]


def month_days(weeks: list[list[dict]], today: date) -> list[dict]:
    """Every day of today's month: its count, or None if it hasn't come yet."""
    counts = {d["date"]: d["count"] for w in weeks for d in w}
    last = calendar.monthrange(today.year, today.month)[1]
    days = []
    for n in range(1, last + 1):
        d = today.replace(day=n)
        days.append({"date": d, "count": counts.get(d, 0) if d <= today else None})
    return days


def stats(days: list[dict], today: date) -> list[tuple[str, str]]:
    past = [d for d in days if d["count"] is not None]
    total = sum(d["count"] for d in past)
    best = max(past, key=lambda d: d["count"])
    streak = 0
    for d in reversed(past):  # today counts if you've contributed; otherwise from yesterday
        if d["count"]:
            streak += 1
        elif d["date"] != today:
            break
    return [
        (f"{total:,}", "This Month"),
        (str(best["count"]), f"Best Day ({best['date']:%b %d})" if best["count"] else "Best Day"),
        (f"{total / len(past):.1f}", "Daily Average"),
        (str(sum(1 for d in past if d["count"])), "Active Days"),
        (f"{streak}d", "Current Streak"),
    ]


def nice_max(v: int) -> int:
    """Round the chart's top up to a friendly number."""
    for step in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if v <= step * 4:
            return max(step, -(-v // step) * step)
    return v


def render(theme: dict, days: list[dict], tiles: list[tuple[str, str]], today: date) -> str:
    ink, bg, lit = theme["text"], theme["bg"], theme["key"]
    right = WIDTH - PAD
    out: list[str] = []
    y = PAD

    # Title and stat tiles.
    out.append(f'<text x="{PAD}" y="{y + 12}" font-size="15" font-weight="bold" fill="{lit}">Contribution Graph</text>'
               f'<text x="{right}" y="{y + 12}" text-anchor="end" font-size="10" fill="{ink}" opacity="0.6">'
               f'daily &#183; {today:%B %Y}</text>')
    y += 26
    tile_w = (right - PAD) / len(tiles)
    for i, (value, label) in enumerate(tiles):
        x = PAD + i * tile_w
        out.append(f'<rect x="{x:.0f}" y="{y + 4}" width="8" height="{TILE_H - 16}" fill="url(#l1)"/>'
                   f'<text x="{x + 16:.0f}" y="{y + 26}" font-size="24" fill="{ink}">{escape(value)}</text>'
                   f'<text x="{x + 16:.0f}" y="{y + 40}" font-size="11" fill="{ink}" opacity="0.8">{escape(label)}</text>')
    y += TILE_H + 44  # headroom for the "Today" marker over a tall bar

    # Chart frame: y axis, dotted guide lines at 0 / half / top.
    counts = [d["count"] for d in days if d["count"] is not None]
    peak = max(counts) or 1
    top = nice_max(peak)
    cx0, cx1 = PAD + AXIS_W, right
    cy0, cy1 = y, y + CHART_H  # top, baseline
    for frac in (0, 0.5, 1):
        gy = round(cy1 - CHART_H * frac)
        out.append(f'<rect x="{cx0}" y="{gy}" width="{cx1 - cx0}" height="1" fill="url(#l0)"/>'
                   f'<text x="{cx0 - 8}" y="{gy + 4}" text-anchor="end" font-size="10" fill="{ink}" '
                   f'opacity="0.6">{round(top * frac)}</text>')

    # One bar per day; x and width on a 4px grid so the dither patterns line up.
    pitch = (cx1 - cx0) / len(days)
    bar_w = max(4, int((pitch - BAR_GAP) // 4 * 4))
    for i, d in enumerate(days):
        x = round((cx0 + i * pitch + (pitch - bar_w) / 2) / 4) * 4
        if d["count"] is None:  # still to come this month
            out.append(f'<rect x="{x}" y="{cy1 - 2}" width="{bar_w}" height="2" fill="url(#l0)"/>')
            continue
        h = round(CHART_H * d["count"] / top)
        share = d["count"] / peak
        fill = lit if share >= 0.75 else "url(#o3)" if share >= 0.5 else "url(#o2)" if share >= 0.25 else "url(#o1)"
        tip = f'{d["date"]:%b %d}: {d["count"]} contribution{"s" * (d["count"] != 1)}'
        out.append(f'<rect x="{x}" y="{cy0}" width="{bar_w}" height="{CHART_H}" fill="transparent"><title>{tip}</title></rect>')
        out.append(f'<rect x="{x}" y="{cy1 - max(h, 2)}" width="{bar_w}" height="{max(h, 2)}" '
                   f'fill="{fill if h else "url(#o1)"}"/>')
        if d["date"] == today:  # a pixel arrow pointing down at today's bar, "Today" above it
            ax, ay = x + bar_w / 2, cy1 - max(h, 2) - 14  # room for the arrow to bob down
            # The arrow bobs down toward the bar and back in 2px steps, retro style.
            bob = ('<animateTransform attributeName="transform" type="translate" '
                   'values="0,0;0,2;0,4;0,2" calcMode="discrete" dur="0.8s" repeatCount="indefinite"/>')
            out.append(f'<g transform="translate({ax},{ay})"><g>{bob}{pixel_art(ARROW, ink, 2)}</g></g>'
                       f'<text x="{ax}" y="{ay - 11}" text-anchor="middle" font-size="11" font-weight="bold" '
                       f'fill="{ink}">Today</text>')

    # Baseline and day numbers (1, every 5th, and the last day).
    out.append(f'<rect x="{cx0}" y="{cy1}" width="{cx1 - cx0}" height="2" fill="{ink}" opacity="0.5"/>')
    for i, d in enumerate(days):
        n = d["date"].day
        if n == 1 or n % 5 == 0 or n == len(days):
            out.append(f'<text x="{round(cx0 + (i + 0.5) * pitch)}" y="{cy1 + 16}" text-anchor="middle" '
                       f'font-size="10" fill="{lit if d["date"] == today else ink}" '
                       f'opacity="{1 if d["date"] == today else 0.75}">{n}</text>')

    height = cy1 + 24 + PAD
    # Grey dither patterns (l0-l3) for guides and placeholders; orange copies (o0-o3) for the bars.
    orange = patterns(lit).replace('id="l', 'id="o')

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
           f'shape-rendering="crispEdges" font-family="Consolas, \'Courier New\', monospace">',
           f"<defs>{patterns(ink)}{orange}</defs>",
           f'<rect width="{WIDTH}" height="{height}" rx="15" fill="{bg}"/>',
           *out, "</svg>"]
    return "\n".join(svg) + "\n"


def main() -> None:
    try:
        weeks = fetch_public_calendar()
    except Exception as err:  # keep yesterday's graph rather than fail the workflow
        print("calendar fetch failed, leaving the graph as it is:", err)
        sys.exit(0)
    today = datetime.now(TZ).date()
    days = month_days(weeks, today)
    tiles = stats(days, today)
    print(f"{today:%B %Y}: {sum(d['count'] or 0 for d in days)} contributions; tiles: {tiles}")
    for name, theme in THEMES.items():
        path = ROOT / f"graph_{name}.svg"
        path.write_text(render(theme, days, tiles, today), encoding="utf-8")
        print("wrote", path.name, f"({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
