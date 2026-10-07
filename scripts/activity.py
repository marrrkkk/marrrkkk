
import calendar
import html
import math
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from common import TZ, Timeline, patterns, pixel_art
from profile_card import PAD, THEMES, USER

ROOT = Path(__file__).resolve().parent.parent
MONTHS = 4                
MAX_ROWS = 5               
WIDTH = 900


TILE_H = 52
LINE_X = PAD + 30          
TEXT_X = LINE_X + 22      
ITEM_X = TEXT_X + 18       
ROW_X = ITEM_X + 14       
HEADER_H = 30
SUMMARY_H = 24
ROW_H = 18
BAR_W = 150
MONTH_GAP = 10

CLIMB = 45
PAUSE = 1.2
FLAG_PAUSE = 1.2
HIT_FREEZE = 0.5
HOP, HOP_TIME = 28, 0.35
GRAVITY = 1400            
STEP = 0.18                
MARIO_PX = 2

# Mario dressed like the photo (assets/me.jpg): black hair (K), fair skin (S),
# dark eyes (E), white shirt (W), navy tie (T), dark trousers (P), shoes (F).
# The darkest tones are lifted a little on the dark card and the white shirt is
# softened on the light card, so nothing vanishes into the background.
MARIO_PALETTE = {
    "dark": {"K": "#4a515b", "S": "#ffe2cc", "E": "#1f2328", "W": "#f0f3f6",
             "T": "#3d5ab8", "P": "#3a4350", "F": "#5a626d"},
    "light": {"K": "#1f2328", "S": "#f6cdb0", "E": "#1f2328", "W": "#d8dee4",
              "T": "#1f3a8a", "P": "#2d333b", "F": "#1f2328"},
}
MARIO_CLIMB = [
    # Hugging the pole on his right, two climbing frames.
    ["....KKKKK...", "...KKKKKKKK.", "...KKKSSES..", "..KKSSSSESSS", "..KKSSSSSSSS",
     "..KSSSSSSSS.", "....SSSSSS..", "...WWTWWWSS.", "..WWWTWWWSS.", "..WWWTTWWW..",
     "..SSWTTWWW..", "..SSWWTWWW..", "...PPPPPP...", "...PPP.PPP..", "..FFF..FFF..",
     ".FFFF...FFF."],
    ["....KKKKK...", "...KKKKKKKK.", "...KKKSSES..", "..KKSSSSESSS", "..KKSSSSSSSS",
     "..KSSSSSSSS.", "....SSSSSSSS", "...WWTWWW.SS", "..WWWTWWW...", ".SWWWTTWWW..",
     ".SSWTTWWWW..", "..SWWWTWWW..", "...PPPPPP...", "..PPP..PPP..", ".FFF...FFF..",
     ".FFFF...FFF."],
]
MARIO_HIT = [  # facing us, arms flung up, mouth open: the Super Mario Bros. "hit" pose
    ".SS......SS.", ".SS.KKKK.SS.", "..KKKKKKKK..", "..KKSSSSKK..", ".KSESSSSESK.",
    ".SSSSSSSSSS.", "..SSSEESSS..", "...SSSSSS...", "..WWWTTWWW..", ".WWWWTTWWWW.",
    ".WWWWTTWWWW.", "..WWWTTWWW..", "..PPP..PPP..", "..PPP..PPP..", ".FFF....FFF.",
    "FFFF....FFFF"]

FLAG_W, FLAG_H, FLAG_PX = 7, 4, 3
WAVE_FRAMES, WAVE_TIME = 4, 0.8

ROCKET_RISE, ROCKET_TIME = 34, 0.35
SPARKS = ((12, 20, "lit"), (6, 10, "ink")) 
BURST_TIME, SPARK_PX, DROOP = 0.6, 3, 6





def fetch_month(year: int, month: int) -> list[dict]:
    """The activity items GitHub lists for one month on the profile."""
    last = calendar.monthrange(year, month)[1]
    url = (f"https://github.com/{USER}?action=show&controller=profiles&tab=contributions"
           f"&from={year}-{month:02d}-01&to={year}-{month:02d}-{last}&user_id={USER}")
    req = urllib.request.Request(url, headers={"X-Requested-With": "XMLHttpRequest",
                                               "User-Agent": "profile-readme"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8")
    start = page.find("contribution-activity-listing")
    if start < 0:
        raise RuntimeError("activity section not found; the profile page layout may have changed")
    end = page.find("Show more activity", start)
    section = page[start:end if end > 0 else None]

    def text(fragment: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()

    items = []
    for block in re.split(r'class="TimelineItem"', section)[1:]:
        head = (re.search(r"<summary[^>]*>\s*<span[^>]*>(.*?)</span>", block, re.S)
                or re.search(r"<h4[^>]*>(.*?)</h4>", block, re.S))
        summary = text(head.group(1)) if head else "Activity"
        summary = re.sub(r"\s+Public$", "", summary)
        rows = []
        for li in re.findall(r"<li\b.*?</li>", block, re.S):
            repo = re.search(r'data-hovercard-type="repository"[^>]*href="/([^"]+)"', li)
            if not repo:
                continue
            count = re.search(r">\s*(\d+) commits?\s*<", li)
            lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', li)
            when = re.search(r"This contribution was made on ([A-Z][a-z]{2} \d+)", li)
            rows.append({"repo": repo.group(1), "count": int(count.group(1)) if count else None,
                         "lang": lang.group(1).strip() if lang else None,
                         "date": when.group(1) if when else None})
        if not rows:  # e.g. a pull request item: the repo is only in the summary
            repo = re.search(r'data-hovercard-type="repository"[^>]*href="/([^"]+)"', block)
            if repo and repo.group(1) not in summary:
                rows.append({"repo": repo.group(1), "count": None, "lang": None, "date": None})
        items.append({"summary": summary, "rows": rows})
    return items


def recent_months(today) -> list[tuple[int, int]]:
    y, m = today.year, today.month
    out = []
    for _ in range(MONTHS):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def totals(months: list[dict]) -> list[tuple[str, str]]:
    commits = repos_made = prs = 0
    active = set()
    for mo in months:
        for it in mo["items"]:
            s = it["summary"].lower()
            if "commit" in s:
                commits += sum(r["count"] or 0 for r in it["rows"])
                active |= {r["repo"] for r in it["rows"]}
            elif s.startswith("created") and "repositor" in s:
                n = re.search(r"created (\d+) repositor", s)
                repos_made += int(n.group(1)) if n else 1
            elif "pull request" in s and "first" not in s:
                prs += 1
    return [(str(commits), "Commits"), (str(len(active)), "Active Repos"),
            (str(repos_made), "Repos Created"), (str(prs), "Pull Requests")]




def mario_art(rows: list[str], palette: dict, px: int = MARIO_PX) -> str:
    """Mario's pixel art in the card palette, anchored at its bottom-right corner."""
    h, w = len(rows), len(rows[0])
    rects: dict[str, list[str]] = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in palette:
                rects.setdefault(ch, []).append(
                    f'<rect x="{(x - w) * px}" y="{(y - h) * px}" width="{px}" height="{px}"/>')
    return "".join(f'<g fill="{palette[c]}">{"".join(r)}</g>' for c, r in rects.items())


def short(repo: str, owner: str = USER) -> str:
    name = repo.split("/", 1)[1] if repo.startswith(owner + "/") else repo
    return name if len(name) <= 34 else name[:33] + "…"


def render(name: str, theme: dict, months: list[dict], stats: list[tuple[str, str]]) -> str:
    ink, bg, pole, lit = theme["text"], theme["bg"], theme["value"], theme["key"]
    palette = MARIO_PALETTE[name]
    right = WIDTH - PAD
    out: list[str] = []
    y = PAD

 
    out.append(f'<text x="{PAD}" y="{y + 12}" font-size="15" font-weight="bold" fill="{lit}">Contribution Activity</text>'
               f'<text x="{right}" y="{y + 12}" text-anchor="end" font-size="10" fill="{ink}" opacity="0.6">'
               f'last {MONTHS} months</text>')
    y += 26
    tile_w = (right - PAD) / len(stats)
    for i, (value, label) in enumerate(stats):
        x = PAD + i * tile_w
        out.append(f'<rect x="{x:.0f}" y="{y + 4}" width="8" height="{TILE_H - 16}" fill="url(#l1)"/>'
                   f'<text x="{x + 16:.0f}" y="{y + 26}" font-size="24" fill="{ink}">{escape(value)}</text>'
                   f'<text x="{x + 16:.0f}" y="{y + 40}" font-size="11" fill="{ink}" opacity="0.8">{escape(label)}</text>')
    y += TILE_H + 70  


    nodes = [] 
    rules = []  
    body: list[str] = []
    for mi, mo in enumerate(months):
        ny = y + HEADER_H // 2
        nodes.append(ny)
        label = f'{calendar.month_name[mo["month"]].upper()} {mo["year"]}'
        lw = len(label) * 7.4
        rules.append((round(TEXT_X + lw + 10), ny, round(right - TEXT_X - lw - 10)))
        body.append(f'<g data-month="{mi}"><text class="m{mi}" x="{TEXT_X}" y="{ny + 4}" font-size="11" '
                    f'font-weight="bold" fill="{ink}">{label}</text></g>'
                    f'<rect x="{TEXT_X + lw + 10:.0f}" y="{ny}" width="{right - TEXT_X - lw - 10:.0f}" height="2" fill="url(#l1)"/>')
        y += HEADER_H
        if not mo["items"]:
            body.append(f'<text x="{ITEM_X}" y="{y + 14}" font-size="11" fill="{ink}" opacity="0.6">'
                        f'No activity this month</text>')
            y += SUMMARY_H
        for it in mo["items"]:
            by = y + SUMMARY_H // 2
            body.append(f'<rect x="{TEXT_X}" y="{by - 5}" width="10" height="10" fill="url(#l2)"/>'
                        f'<text x="{ITEM_X}" y="{by + 4}" font-size="12.5" fill="{ink}">{escape(it["summary"])}</text>')
            y += SUMMARY_H
            rows = it["rows"]
            top = max((r["count"] or 0) for r in rows) if rows else 0
            total = sum(r["count"] or 0 for r in rows)
            for r in rows[:MAX_ROWS]:
                ry = y + ROW_H // 2 + 4
                body.append(f'<text x="{ROW_X}" y="{ry}" font-size="11" fill="{pole}">{escape(short(r["repo"]))}</text>')
                if r["count"] is not None:
                    share = r["count"] / total if total else 0
                    fill = ink if share >= 0.4 else "url(#l3)" if share >= 0.2 else "url(#l2)" if share >= 0.1 else "url(#l1)"
                    bw = max(4, round(BAR_W * r["count"] / top / 4) * 4)
                    body.append(f'<text x="{right - BAR_W - 10}" y="{ry}" text-anchor="end" font-size="11" '
                                f'fill="{ink}" opacity="0.75">{r["count"]} commit{"s" * (r["count"] != 1)}</text>'
                                f'<rect x="{right - BAR_W}" y="{ry - 9}" width="{BAR_W}" height="10" fill="url(#l0)"/>'
                                f'<rect x="{right - BAR_W}" y="{ry - 9}" width="{bw}" height="10" fill="{fill}"/>')
                else:
                    meta = " &#183; ".join(escape(v) for v in (r["lang"], r["date"]) if v)
                    if meta:
                        body.append(f'<text x="{right}" y="{ry}" text-anchor="end" font-size="11" '
                                    f'fill="{ink}" opacity="0.75">{meta}</text>')
                y += ROW_H
            if len(rows) > MAX_ROWS:
                body.append(f'<text x="{ROW_X}" y="{y + ROW_H // 2 + 4}" font-size="11" fill="{ink}" '
                            f'opacity="0.6">+{len(rows) - MAX_ROWS} more</text>')
                y += ROW_H
            y += 4
        y += MONTH_GAP
    bottom = y - MONTH_GAP
    height = bottom + PAD

    pole_top = nodes[0] - 34
    stops = sorted(nodes, reverse=True) + [pole_top + 10]
    t, pos = 0.0, bottom
    keys = [(0.0, bottom)]
    reached = {}
    climbing = []  
    for i, sy in enumerate(stops):
        dt = (pos - sy) / CLIMB
        climbing.append((t, t + dt))
        t += dt
        keys.append((t, sy))
        if i < len(nodes):
            reached[len(nodes) - 1 - i] = t  
        t += FLAG_PAUSE if i == len(stops) - 1 else PAUSE
        keys.append((t, sy))
        pos = sy
    flag_at = keys[-2][0]
    approach = {len(nodes) - 1 - i: climbing[i] for i in range(len(nodes))}

    top = stops[-1]
    hit_at = t
    t += HIT_FREEZE
    keys.append((t, top))
    t += HOP_TIME
    keys.append((t, top - HOP))
    drop = height + 40 - (top - HOP) 
    fall_time = (2 * drop / GRAVITY) ** 0.5
    for j in range(1, 9):  
        dt = fall_time * j / 8
        keys.append((t + dt, top - HOP + 0.5 * GRAVITY * dt * dt))
    t += fall_time
    dur = t + 0.6 
    tl = Timeline(dur)

    for mi, at in reached.items():
        old = f'<text class="m{mi}"'
        i = next(j for j, b in enumerate(body) if old in b)
        label_el = re.search(r'<text class="m%d".*?</text>' % mi, body[i]).group(0)
        lit_el = (label_el.replace(f'fill="{ink}"', f'fill="{lit}" opacity="0"')
                  .replace("</text>", tl.show([(0, False), (at, True)]) + "</text>"))
        body[i] = body[i].replace(label_el, label_el + lit_el)

    for mi, (rx, ry, rw) in enumerate(rules):
        start, end = approach[mi]
        # Fills right to left: the left edge slides from the rule's far end to
        # the month name while the width grows to match.
        timing = f'keyTimes="0;{tl.key(start)};{tl.key(end)};1" calcMode="linear" {tl.loop}'
        body.append(f'<rect x="{rx + rw}" y="{ry}" width="0" height="2" fill="url(#l1o)">'
                    f'<animate attributeName="x" values="{rx + rw};{rx + rw};{rx};{rx}" {timing}/>'
                    f'<animate attributeName="width" values="0;0;{rw};{rw}" {timing}/></rect>')

    frames = []
    for j, art in enumerate(MARIO_CLIMB):
        changes = [(0.0, j == 0)]
        for a, b in climbing:
            k = 0
            while a + k * STEP < b:
                changes.append((a + k * STEP, k % 2 == j))
                k += 1
            changes.append((b, j == 0))
        changes.append((hit_at, False))  
        frames.append(f'<g opacity="0">{tl.show(changes)}{mario_art(art, palette)}</g>')
    frames.append(f'<g opacity="0">{tl.show([(0, False), (hit_at, True), (t, False)])}'
                  f'<g transform="translate({len(MARIO_HIT[0]) * MARIO_PX // 2},0)">'
                  f'{mario_art(MARIO_HIT, palette)}</g></g>')
    motion = tl.motion([k for k, _ in keys], [(LINE_X + 1, v + 16) for _, v in keys])

    wave = []
    for f in range(WAVE_FRAMES):
        cells = []
        for c in range(FLAG_W):
            bob = round(math.sin(2 * math.pi * (c / FLAG_W - f / WAVE_FRAMES)) * min(1, c / 3))
            cells += [f'<rect x="{c * FLAG_PX}" y="{(r + bob) * FLAG_PX}" width="{FLAG_PX}" height="{FLAG_PX}"/>'
                      for r in range(FLAG_H)]
        keys = ";".join("1" if g == f else "0" for g in range(WAVE_FRAMES))
        wave.append(f'<g opacity="0">{"".join(cells)}<animate attributeName="opacity" values="{keys}" '
                    f'calcMode="discrete" dur="{WAVE_TIME}s" repeatCount="indefinite"/></g>')
    flag = (f'<g transform="translate({LINE_X + 1},{pole_top})" fill="{lit}">'
            f'<animate attributeName="fill" {tl.steps([(0, lit), (flag_at, ink), (dur, ink)])}/>'
            f'{"".join(wave)}</g>')

    fx, fy = LINE_X + 1 + FLAG_W * FLAG_PX // 2, pole_top - 4
    burst_at = flag_at + ROCKET_TIME
    by = fy - ROCKET_RISE
    rocket = (f'<g opacity="0">{tl.show([(0, False), (flag_at, True), (burst_at, False)])}'
              f'{tl.motion([flag_at, burst_at], [(fx, fy), (fx, by)])}'
              f'<rect x="-1" y="-2" width="2" height="4" fill="{lit}"/>'
              f'<rect x="-1" y="2" width="2" height="4" fill="{lit}" opacity="0.4"/></g>')
    colours = {"lit": lit, "ink": ink}
    sparks = []
    end = burst_at + BURST_TIME
    for count, radius, colour in SPARKS:
        for k in range(count):
            ang = 2 * math.pi * k / count
            dx, dy = round(radius * math.cos(ang)), round(radius * math.sin(ang))

            flicker = [(0, False), (burst_at, True)] + [
                (burst_at + BURST_TIME * 0.55 + 0.05 * f, f % 2 == 1) for f in range(int(BURST_TIME * 0.45 / 0.05))
            ] + [(end, False)]
            sparks.append(
                f'<g opacity="0">{tl.show(flicker)}'
                f'{tl.motion([burst_at, burst_at + 0.25, end], [(fx, by), (fx + dx, by + dy), (fx + dx, by + dy + DROOP)])}'
                f'<rect x="{-SPARK_PX // 2}" y="{-SPARK_PX // 2}" width="{SPARK_PX}" height="{SPARK_PX}" '
                f'fill="{colours[colour]}"/></g>')
    firework = rocket + "".join(sparks)

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
        f'shape-rendering="crispEdges" font-family="Consolas, \'Courier New\', monospace">',
        f'<defs>{patterns(ink)}<pattern id="l1o" width="4" height="4" patternUnits="userSpaceOnUse">'
        f'<rect width="2" height="2" fill="{lit}"/></pattern></defs>',
        f'<rect width="{WIDTH}" height="{height}" rx="15" fill="{bg}"/>',
        *out,
        f'<rect x="{LINE_X - 1}" y="{pole_top}" width="2" height="{bottom - pole_top}" fill="{lit}"/>',
        f'<rect x="{LINE_X - 3}" y="{pole_top - 4}" width="6" height="6" fill="{lit}"/>',
        flag,
        firework,
        *(f'<rect x="{LINE_X - 4}" y="{ny - 4}" width="8" height="8" fill="{ink}"/>' for ny in nodes),
        *body,
        f"<g>{motion}{''.join(frames)}</g>",
        "</svg>",
    ]
    return "\n".join(svg) + "\n"


def main() -> None:
    today = datetime.now(TZ).date()
    try:
        months = [{"year": y, "month": m, "items": fetch_month(y, m)} for y, m in recent_months(today)]
    except Exception as err:  
        print("activity fetch failed, leaving the cards as they are:", err)
        sys.exit(0)
    for mo in months:
        print(f'{mo["year"]}-{mo["month"]:02d}:', "; ".join(i["summary"] for i in mo["items"]) or "no activity")
    stats = totals(months)
    print("tiles:", stats)
    for name, theme in THEMES.items():
        path = ROOT / f"activity_{name}.svg"
        path.write_text(render(name, theme, months, stats), encoding="utf-8")
        print("wrote", path.name, f"({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
