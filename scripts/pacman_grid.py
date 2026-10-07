import argparse
import os
import random
import re
import urllib.request
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from profile_card import PAD, THEMES, USER, graphql

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Asia/Manila")


PX = 2
CELL_W, CELL_H = 12, 24
COL, ROW = 16, 28          # pitch
TILE_H = 56
TILES_GAP = 24
MONTH_H = 24
WALL_CHANCE = 0.45         # share of gutters that try to become walls
HOUSE_W, HOUSE_H, HOUSE_ROW = 6, 3, 2  # ghost house: 6x3 days, rows 2-4, mid-year
POWER_PELLETS = 4          # biggest days become power pellets

# Game timing. One tick = every sprite moves at most one day.
TICK = 0.24                # s per tick
READY = 2.0                # s everyone sits in the ghost house first
GHOST_FILLS = ("solid", "l3", "l2", "l1")
FLASH = 8                  #ghosts flash for the last ticks of their fright
RESPAWN = 10               #ticks eaten ghosts wait in the house before rejoining
EYE_BERTH = 3              #pacman keeps off eaten ghosts' eyes and this many cells of their way home
MAX_TICKS = 700            #per-level stalemate cap (~3 min): TIME UP
LIVES = 3                  #a ghost touch costs one; the last one is GAME OVER
FREEZE_TICKS = 3           #everything stops when Pac-Man is caught
RESPAWN_READY = 8          #and after a lost life, READY! in the house for this long
END_PAUSE = 3.0            #showing GAME OVER / YOU WIN! before the reset
WALL_FLASH = 1.6           #the maze flashes after a level is cleared
JUMP = 0.1                 #sprites are hidden while they hop back to the house

LEVEL_CFG = (
    {"release": (0, 12, 24, 36), "fright": 28, "waves": (29, 83, 29, 83, 21, 83, 21)},
    {"release": (0, 8, 16, 24), "fright": 22, "waves": (25, 100, 25, 100, 17)},
    {"release": (0, 4, 8, 12), "fright": 16, "waves": (21, 120, 17, 120, 4)},
)
AMBUSH = 4

PAC_COLOURS = {
    "dark": ("#ff7b72", "#d2a8ff", "#7ee787", "#79c0ff", "#f2cc60", "#ff9bce", "#56d4dd"),
    "light": ("#cf222e", "#8250df", "#1a7f37", "#0969da", "#9a6700", "#bf3989", "#1b7c83"),
}
COLOUR_CYCLE = 6           

MATCHES = 4               
DEFAULT_POLICY = {"margin": 1, "avoid": 0, "power": 0}
AVOID_STEPS = (0, 1, 2, 4)
MEMORY_RADIUS = 2       
DANGER_MARK = ["#...#", ".#.#.", "..#..", ".#.#.", "#...#"]

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

CALENDAR_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""

PACMAN_OPEN = ["..###..", ".#####.", "####...", "###....", "####...", ".#####.", "..###.."]
PACMAN_SHUT = ["..###..", ".#####.", "#######", "#######", "#######", ".#####.", "..###.."]
PACMAN_DEATH = [  # mouth opens upward until he's gone
    [".......", ".#...#.", "##...##", "###.###", "#######", ".#####.", "..###.."],
    [".......", ".......", "#.....#", "##...##", "#######", ".#####.", "..###.."],
    [".......", ".......", ".......", "#.....#", "##...##", ".#####.", "..###.."],
    [".......", ".......", ".......", ".......", ".......", ".#...#.", "..###.."],
    [".......", ".......", ".......", ".......", ".......", ".......", "...#..."],
]
GHOST = ["..###..", ".#####.", "#.##.##", "#######", "#######", "#######", "#.#.#.#"]
GHOST_SCARED = ["..###..", ".#####.", "##.#.##", "#######", "#.#.#.#", "#######", "#.#.#.#"]
GHOST_EYES = [".......", ".......", "##..##.", "##..##.", ".......", ".......", "......."]
POWER = [".##.", "####", "####", ".##."]
ANGLE = {(1, 0): 0, (0, 1): 90, (-1, 0): 180, (0, -1): 270}




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


def fetch_api_calendar(token: str) -> list[list[dict]]:
    data = graphql(token, CALENDAR_QUERY, {"login": USER})
    weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return to_weeks([day(date.fromisoformat(d["date"]), d["contributionCount"], LEVELS[d["contributionLevel"]])
                     for w in weeks for d in w["contributionDays"]])


def fake_calendar(today: date) -> list[list[dict]]:
    rng = random.Random(7)
    days = []
    for i in range(365):
        d = today - timedelta(days=364 - i)
        count = rng.choice([1, 2, 3, 5, 8, 13]) if rng.random() < 0.2 else 0
        days.append(day(d, count, 0 if not count else min(4, 1 + count // 4)))
    return to_weeks(days)


def tiles(weeks: list[list[dict]], today: date) -> list[tuple[str, str]]:
    days = {d["date"]: d["count"] for w in weeks for d in w}

    def total(start: date, end: date = today) -> int:
        return sum(c for d, c in days.items() if start <= d <= end)

    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    streak, d = 0, today if days.get(today) else today - timedelta(days=1)
    while days.get(d):
        streak, d = streak + 1, d - timedelta(days=1)
    return [
        (str(days.get(today, 0)), "Today"),
        (str(days.get(today - timedelta(days=1), 0)), "Yesterday"),
        (str(total(today - timedelta(days=today.weekday()))), "This Week"),
        (str(total(today - timedelta(days=6))), "Last 7 Days"),
        (f"{streak}d", "Current Streak"),
        (str(total(month_start)), "This Month"),
        (str(total(last_month_end.replace(day=1), last_month_end)), "Last Month"),
        (str(total(today - timedelta(days=29))), "Last 30 Days"),
        (str(total(today - timedelta(days=89))), "Last 3 Months"),
        (f"{sum(days.values()):,}", "Last Year"),
    ]



def grid_graph(weeks: list[list[dict]]) -> dict[tuple, set]:
    nodes = {(w, d["weekday"]) for w, week in enumerate(weeks) for d in week}
    return {n: {m for m in ((n[0] + 1, n[1]), (n[0] - 1, n[1]), (n[0], n[1] + 1), (n[0], n[1] - 1))
                if m in nodes} for n in nodes}


def connected(graph: dict[tuple, set]) -> bool:
    start = next(iter(graph))
    seen, todo = {start}, [start]
    while todo:
        for m in graph[todo.pop()] - seen:
            seen.add(m)
            todo.append(m)
    return len(seen) == len(graph)


def ghost_house(weeks: list[list[dict]]) -> dict:
    """A walled box mid-year with a two-cell open door on top, and a wall-free
    lobby above it (one column wider each side) so the way out is always clear."""
    c0 = len(weeks) // 2 - HOUSE_W // 2
    cells = {(c0 + x, HOUSE_ROW + y) for x in range(HOUSE_W) for y in range(HOUSE_H)}
    door_cols = (c0 + HOUSE_W // 2 - 1, c0 + HOUSE_W // 2)
    doors = {frozenset(((c, HOUSE_ROW - 1), (c, HOUSE_ROW))) for c in door_cols}
    mid = HOUSE_ROW + HOUSE_H // 2
    return {
        "cells": cells,
        "doors": doors,
        "lobby": {(c, r) for c in range(c0 - 1, c0 + HOUSE_W + 1) for r in range(HOUSE_ROW)},
        "exit": (door_cols[0], HOUSE_ROW - 1),  # just outside the door
        "start": (door_cols[0], mid),
        "slots": [(c0, mid), (c0 + 1, mid), (c0 + HOUSE_W - 2, mid), (c0 + HOUSE_W - 1, mid)],
    }


def build_maze(graph: dict[tuple, set], rng: random.Random, house: dict) -> set[frozenset]:
    """Knock walls into gutters at random, never leaving a dead end or cutting the maze in two.

    The ghost house is fixed: walled all round except its door, open inside,
    and nothing is ever walled off inside the lobby above it."""
    walls = set()
    inside = house["cells"]
    for a in inside:
        for b in list(graph[a]):
            edge = frozenset((a, b))
            if b not in inside and edge not in house["doors"]:
                graph[a].discard(b)
                graph[b].discard(a)
                walls.add(edge)
    edges = sorted({frozenset((a, b)) for a in graph for b in graph[a]}, key=sorted)
    rng.shuffle(edges)
    for edge in edges:
        a, b = tuple(edge)
        if a in inside or b in inside or edge in house["doors"]:
            continue
        if a in house["lobby"] and b in house["lobby"]:
            continue
        if rng.random() > WALL_CHANCE or len(graph[a]) <= 2 or len(graph[b]) <= 2:
            continue
        graph[a].discard(b)
        graph[b].discard(a)
        if connected(graph):
            walls.add(edge)
        else:
            graph[a].add(b)
            graph[b].add(a)
    return walls


def bfs(graph: dict[tuple, set], start: tuple, targets, blocked=frozenset()) -> list[tuple] | None:
    """Shortest path from start to the nearest target, avoiding blocked nodes."""
    targets = targets if isinstance(targets, (set, frozenset)) else {targets}
    prev, todo = {start: None}, deque([start])
    while todo:
        n = todo.popleft()
        if n in targets:
            path = []
            while n is not None:
                path.append(n)
                n = prev[n]
            return path[::-1]
        for m in sorted(graph[n]):
            if m not in prev and m not in blocked:
                prev[m] = n
                todo.append(m)
    return None


def distances(graph: dict[tuple, set], start: tuple) -> dict[tuple, int]:
    dist, todo = {start: 0}, deque([start])
    while todo:
        n = todo.popleft()
        for m in graph[n]:
            if m not in dist:
                dist[m] = dist[n] + 1
                todo.append(m)
    return dist



def simulate(graph, house, pellets, power, rng, cfg: dict, lives: int,
             policy: dict = DEFAULT_POLICY, memory: dict | None = None) -> dict:
    """Play one level with `lives` left, Pac-Man using `policy` and his
    `memory` of dangerous days. Returns per-tick frames (deaths and respawn
    READY pauses included), eat times, the outcome, lives left and where he
    was caught."""
    memory = memory or {}
    inside = frozenset(house["cells"])
    cols = max(n[0] for n in graph)
    corners = [min(graph, key=lambda n: abs(n[0] - cx) + abs(n[1] - cy))
               for cx, cy in ((cols, 0), (0, 0), (cols, 6), (0, 6))]
    left = set(pellets)
    eaten_at: dict[tuple, int] = {}
    frames: list[dict] = []
    ghosts = [{} for _ in house["slots"]]
    st = {"ghosts_eaten": 0, "deaths": 0, "caught_at": []}

    def spawn(k0: int):
        """Everyone back in the house; ghosts released relative to tick k0."""
        st.update(pac=house["start"], facing=(1, 0), fright_until=-1, wave_start=k0, was_scatter=True)
        for g, slot, r in zip(ghosts, house["slots"], cfg["release"]):
            g.clear()
            g.update(at=slot, prev=slot, mode="house", release=k0 + r, scared=False, last=None)

    def look(g, k):
        if g["mode"] == "eyes":
            return "eyes"
        if g["scared"]:
            return "flash" if st["fright_until"] - k <= FLASH and k % 2 else "scared"
        return "normal"

    def snap(pac_look="alive", ghosts_hidden=False, sign=None):
        k = len(frames)
        frames.append({
            "pac": st["pac"], "facing": st["facing"], "pac_look": pac_look, "sign": sign, "lives": lives,
            "ghosts": [(g["at"], "hidden" if ghosts_hidden else look(g, k), g["mode"] == "house")
                       for g in ghosts],
        })

    spawn(0)
    if st["pac"] in left:
        left.discard(st["pac"])
        eaten_at[st["pac"]] = 0
    snap()
    outcome = "clear"

    while left:
        k = len(frames)
        if k > MAX_TICKS:
            outcome = "time"
            break
        pac, facing = st["pac"], st["facing"]

        hunters = [g for g in ghosts if g["mode"] in ("roam", "leaving") and not g["scared"]]
        prey = {g["at"] for g in ghosts if g["mode"] == "roam" and g["scared"]}
        blocked = set() if pac in inside else set(inside)
        ghost_eta: dict[tuple, int] = {}
        for g in hunters:
            for n, d in distances(graph, g["at"]).items():
                ghost_eta[n] = min(d, ghost_eta.get(n, 999))
        # Eaten ghosts are just eyes heading home: leave them be. Their cell
        # and the next few on their way back are off his map, so he never
        # trails along behind them (unless that would leave him stuck).
        eye_zone = set()
        for i, g in enumerate(ghosts):
            if g["mode"] == "eyes":
                home = bfs(graph, g["at"], house["slots"][i]) or [g["at"]]
                eye_zone |= set(home[:EYE_BERTH + 1])
        eye_zone.discard(pac)

        def plan(no_go: set) -> tuple[dict, dict]:
            prev, depth, todo = {pac: None}, {pac: 0}, deque([pac])
            while todo:
                n = todo.popleft()
                for m in sorted(graph[n]):
                    t = depth[n] + 1
                    lead = policy["margin"] + policy["avoid"] * memory.get(m, 0) / 3  
                    if m in prev or m in no_go or t + lead >= ghost_eta.get(m, 999):
                        continue
                    prev[m], depth[m] = n, t
                    todo.append(m)
            return prev, depth

        prev, depth = plan(blocked | eye_zone)
        if len(prev) == 1 and eye_zone: 
            prev, depth = plan(blocked)

        def first_step(goal):
            while prev[goal] != pac:
                goal = prev[goal]
            return goal

        safe = [n for n in prev if n != pac]
        close = ghost_eta.get(pac, 999) <= 6

        def cost(n):
            c = depth[n] + policy["avoid"] * memory.get(n, 0)
            if policy["power"] and n in power:
                c += -8 if close else 30
            return c

        goals = [n for n in safe if n in prey] or [n for n in safe if n in left]
        if goals:
            step = first_step(min(goals, key=lambda n: (cost(n), n)))
        elif safe: 
            step = first_step(max(safe, key=lambda n: (ghost_eta.get(n, 999) - policy["avoid"] * memory.get(n, 0),
                                                       -depth[n], n)))
        else: 
            moves = [n for n in graph[pac] if n not in blocked] or [pac]
            step = max(sorted(moves), key=lambda n: ghost_eta.get(n, 999))
        pac_prev, pac = pac, step
        if pac != pac_prev:
            facing = (pac[0] - pac_prev[0], pac[1] - pac_prev[1])
        st.update(pac=pac, facing=facing)
        if pac in left:
            left.discard(pac)
            eaten_at[pac] = k
            if pac in power:
                st["fright_until"] = k + cfg["fright"]
                for g in ghosts:
                    g["scared"] = g["mode"] != "eyes"
                    g["last"] = None  
        if k >= st["fright_until"]:
            for g in ghosts:
                g["scared"] = False

        to_pac = distances(graph, pac)
        elapsed, scatter = k - st["wave_start"], True
        for wave in cfg["waves"]:
            if elapsed < wave:
                break
            elapsed -= wave
            scatter = not scatter
        else:
            scatter = False
        if scatter != st["was_scatter"]:  
            for g in ghosts:
                g["last"] = None
        st["was_scatter"] = scatter

        def target(i: int) -> tuple:
            """Where ghost i is heading: its corner when scattering, else
            chaser, ambusher, flanker, chaser."""
            if scatter:
                return corners[i]
            aim = pac
            if i == 1: 
                for ahead_n in range(1, AMBUSH + 1):
                    ahead = (pac[0] + facing[0] * ahead_n, pac[1] + facing[1] * ahead_n)
                    if ahead in graph and ahead not in inside:
                        aim = ahead
            elif i == 2:  
                g0 = ghosts[0]["at"]
                far = (2 * pac[0] - g0[0], 2 * pac[1] - g0[1])
                if far in graph and far not in inside:
                    aim = far
            return aim

        wants: dict[int, list[tuple]] = {}
        for i, g in enumerate(ghosts):
            g["prev"] = g["at"]
            mode = g["mode"]
            if mode == "house":
                if k >= g["release"]:
                    g["mode"] = "leaving"
                continue
            if mode == "leaving":
                path = bfs(graph, g["at"], house["exit"])
                if path and len(path) > 1:
                    wants[i] = [path[1]]
                continue
            if mode == "eyes":
                slot = house["slots"][i]
                path = bfs(graph, g["at"], slot)
                g["at"] = path[1] if path and len(path) > 1 else slot
                if g["at"] == slot:
                    g.update(mode="house", release=k + RESPAWN)
                continue
            # roam
            options = [n for n in sorted(graph[g["at"]]) if n not in inside]
            forward = [n for n in options if n != g.get("last")] or options
            back = [n for n in options if n not in forward]  
            if g["scared"]:
                if k % 2:  
                    continue
                rank = sorted(forward, key=lambda n: (-to_pac.get(n, 0), rng.random()))
            else:  
                aim = target(i)
                to_aim = to_pac if aim == pac else distances(graph, aim)
                rank = sorted(forward, key=lambda n: (to_aim.get(n, 99), rng.random()))
            wants[i] = rank + back

        solid = [g for g in ghosts if g["mode"] != "eyes"]
        pending = dict(wants)
        for _ in range(len(ghosts) + 1):  
            moved = False
            for i, choices in list(pending.items()):
                g = ghosts[i]
                for cell in choices:
                    holder = next((o for o in solid if o is not g and o["at"] == cell), None)
                    if holder is None:
                        g["at"] = cell
                        del pending[i]
                        moved = True
                        break
                    j = ghosts.index(holder)
                    if j in pending and g["at"] not in pending[j][:1]:
                        break 
            if not moved:
                break
        for i in wants:
            if ghosts[i]["mode"] == "roam" and ghosts[i]["at"] != ghosts[i]["prev"]:
                ghosts[i]["last"] = ghosts[i]["prev"]
        for g in ghosts:
            if g["mode"] == "leaving" and g["at"] == house["exit"]:
                g["mode"] = "roam"

       
        caught = False
        for g in ghosts:
            if g["mode"] not in ("roam", "leaving"):
                continue
            if not (g["at"] == pac or (g["at"] == pac_prev and g["prev"] == pac)):
                continue
            if g["scared"]:
                g.update(mode="eyes", scared=False)
                st["ghosts_eaten"] += 1
            else:
                caught = True
        snap()
        if not caught:
            continue

      
        lives -= 1
        st["deaths"] += 1
        st["caught_at"].append(pac)
        for _ in range(FREEZE_TICKS):
            snap()
        for j in range(len(PACMAN_DEATH)):
            snap(pac_look=f"die{j}", ghosts_hidden=True)
        if lives == 0:
            snap(pac_look="hidden", ghosts_hidden=True)
            outcome = "over"
            break
        snap(pac_look="hidden", ghosts_hidden=True) 
        spawn(len(frames) + RESPAWN_READY)
        for _ in range(RESPAWN_READY):
            snap(sign="READY!")

    return {"frames": frames, "eaten_at": eaten_at, "outcome": outcome, "lives": lives,
            "ghosts_eaten": st["ghosts_eaten"], "deaths": st["deaths"], "caught_at": st["caught_at"]}


def play(weeks: list[list[dict]], seed: int, policy: dict = DEFAULT_POLICY, memory: dict | None = None):
    
    by_node = {(w, d["weekday"]): d for w, week in enumerate(weeks) for d in week}
    house = ghost_house(weeks)
    pellets = {n for n, d in by_node.items() if d["count"] and n not in house["cells"]}
    power = set(sorted(pellets, key=lambda n: (-by_node[n]["count"], n))[:POWER_PELLETS])
    levels, lives = [], LIVES
    for number, cfg in enumerate(LEVEL_CFG, 1):
        rng = random.Random(seed * 10 + number)
        graph = grid_graph(weeks)
        walls = build_maze(graph, rng, house)
        game = simulate(graph, house, pellets, power, rng, cfg, lives, policy, memory)
        lives = game["lives"]
        levels.append({"number": number, "walls": walls, "game": game})
        if game["outcome"] != "clear":
            break
    return house, pellets, power, levels


def run_score(levels: list[dict]) -> float:
    
    last = levels[-1]["game"]
    return (1000 * sum(lv["game"]["outcome"] == "clear" for lv in levels)
            + 10 * len(last["eaten_at"]) + 15 * sum(lv["game"]["ghosts_eaten"] for lv in levels)
            + 200 * last["lives"] - 500 * (last["outcome"] == "time"))


def learn(weeks: list[list[dict]], seed: int) -> dict:
    
    policy, memory = dict(DEFAULT_POLICY), {}
    house, pellets, power, levels = play(weeks, seed, policy, memory)
    matches = [{"policy": policy, "memory": {}, "levels": levels, "learned_from": 0, "score": run_score(levels)}]
    for _ in range(MATCHES - 1):
        prev = matches[-1]
        memory = dict(prev["memory"])
        for lv in prev["levels"]:
            for cx, cy in lv["game"]["caught_at"]:
                for dx in range(-MEMORY_RADIUS, MEMORY_RADIUS + 1):
                    for dy in range(-MEMORY_RADIUS, MEMORY_RADIUS + 1):
                        dist = abs(dx) + abs(dy)
                        if dist <= MEMORY_RADIUS:
                            n = (cx + dx, cy + dy)
                            memory[n] = memory.get(n, 0) + 3 / (1 + dist)
        margins = sorted({max(0, prev["policy"]["margin"] - 1), prev["policy"]["margin"],
                          min(3, prev["policy"]["margin"] + 1)})
        tried = [(prev["score"], False, prev["policy"], prev["levels"])]  
        for margin in margins:
            for avoid in AVOID_STEPS:
                for pw in (0, 1):
                    cand = {"margin": margin, "avoid": avoid, "power": pw}
                    *_, lv = play(weeks, seed, cand, memory)
                    tried.append((run_score(lv), True, cand, lv))
       
        score, _, policy, levels = max(tried, key=lambda x: (x[0], x[1]))
        if score <= prev["score"]:
            break
        deaths = prev["learned_from"] + sum(lv["game"]["deaths"] for lv in prev["levels"])
        matches.append({"policy": policy, "memory": memory, "levels": levels,
                        "learned_from": deaths, "score": score})
    return {"house": house, "pellets": pellets, "power": power, "matches": matches}


def pick_run(weeks: list[list[dict]], day_seed: int, tries: int = 12, finalists: int = 3) -> tuple[int, dict]:
    """Pick the day's game: audition rookie matches, keep a few where the
    rookie struggles on level 1 or 2 (room to learn), let Pac-Man learn on
    each, and keep the one where he improves most (a win is a bonus)."""
    def rookie(seed: int) -> float:
        *_, lv = play(weeks, seed)
        last = lv[-1]["game"]
        ticks = sum(len(x["game"]["frames"]) for x in lv)
        return (300 * (len(lv) <= 2 and last["outcome"] == "over")
                + len(last["eaten_at"]) - max(0, ticks - 900) / 10 - 500 * (last["outcome"] == "time"))
    seeds = sorted((day_seed * 100 + j for j in range(tries)), key=rookie, reverse=True)[:finalists]
    best = None
    for seed in seeds:
        data = learn(weeks, seed)
        scores = [m["score"] for m in data["matches"]]
        arc = scores[-1] - scores[0] + 300 * (data["matches"][-1]["levels"][-1]["game"]["outcome"] == "clear")
        if best is None or arc > best[0]:
            best = (arc, seed, data)
    return best[1], best[2]




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


def fill_for(level: int, ink: str) -> str:
    return ink if level >= 4 else f"url(#l{max(level, 1)})"


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


def render(name: str, theme: dict, weeks: list[list[dict]], stats: list[tuple[str, str]], seed: int,
           data: dict) -> str:
    ink, bg, accent, wall = theme["text"], theme["bg"], theme["key"], theme["value"]
    grid_w = len(weeks) * COL - (COL - CELL_W)
    width = PAD * 2 + grid_w
    grid_top = PAD + 2 * TILE_H + TILES_GAP
    height = grid_top + 7 * ROW + MONTH_H + PAD // 2
    by_node = {(w, d["weekday"]): d for w, week in enumerate(weeks) for d in week}

    def cell_xy(n: tuple) -> tuple[int, int]:
        return PAD + n[0] * COL, grid_top + n[1] * ROW

    def centre(n: tuple) -> tuple[int, int]:
        x, y = cell_xy(n)
        return x + CELL_W // 2, y + CELL_H // 2

    house, pellets, power, matches = data["house"], data["pellets"], data["power"], data["matches"]
    levels = []
    t = 0.0
    for m, match in enumerate(matches):
        match["start"] = t
        for i, src in enumerate(match["levels"]):
            lv = {**src, "match": m, "last": i == len(match["levels"]) - 1}
            g = lv["game"]
            lv["start"], lv["play"] = t, t + READY
            lv["end"] = lv["play"] + (len(g["frames"]) - 1) * TICK
            lv["tick"] = lambda k, lv=lv: lv["play"] + k * TICK
            if g["outcome"] == "clear":  
                lv["flash"] = (lv["end"] + 0.4, lv["end"] + 0.4 + WALL_FLASH)
            if lv["last"]:
                match["outcome"] = g["outcome"]
                match["result_at"] = lv["flash"][1] if "flash" in lv else lv["end"] + 0.4
                match["end"] = t = match["result_at"] + END_PAUSE
            else:
                t = lv["flash"][1] + JUMP
            levels.append(lv)
    for a, b in zip(levels, levels[1:]):
        a["next"] = b["start"]
    dur = matches[-1]["end"]
    for lv in levels:
        lv["stop"] = lv.get("next", dur)
    tl = Timeline(dur)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" shape-rendering="crispEdges" '
        f'font-family="Consolas, \'Courier New\', monospace">',
        f"<defs>{patterns(ink)}</defs>",
        f'<rect width="{width}" height="{height}" rx="15" fill="{bg}"/>',
    ]

    tile_w = grid_w / 5
    for i, (value, label) in enumerate(stats):
        x = PAD + (i % 5) * tile_w
        y = PAD + (i // 5) * TILE_H
        out.append(
            f'<rect x="{x:.0f}" y="{y + 4}" width="8" height="{TILE_H - 16}" fill="url(#l1)"/>'
            f'<text x="{x + 16:.0f}" y="{y + 26}" font-size="24" fill="{ink}">{escape(value)}</text>'
            f'<text x="{x + 16:.0f}" y="{y + 40}" font-size="11" fill="{ink}" opacity="0.8">{escape(label)}</text>'
        )

    for n, d in sorted(by_node.items()):
        x, y = cell_xy(n)
        c = d["count"]
        floor = "none" if n in house["cells"] else "url(#l0)"
        out.append(f'<rect x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}" fill="{floor}" pointer-events="all">'
                   f'<title>{d["date"]:%b %d}: {c} contribution{"s" * (c != 1)}</title></rect>')

    fx, fy = PAD - 3, grid_top - 3
    out.append(f'<rect x="{fx}" y="{fy}" width="{grid_w + 6}" height="{7 * ROW - (ROW - CELL_H) + 6}" '
               f'fill="none" stroke="{wall}" stroke-width="2"/>')
    for lv in levels:
        bars = []
        for edge in lv["walls"]:
            a, b = sorted(edge)
            x, y = cell_xy(a)
            if a[0] != b[0]:   
                bars.append(f'<rect x="{x + CELL_W + 1}" y="{y - 2}" width="2" height="{ROW}"/>')
            else:             
                bars.append(f'<rect x="{x - 2}" y="{y + CELL_H + 1}" width="{COL}" height="2"/>')
        shown = [(0, lv is levels[0]), (lv["start"], True)]
        if "flash" in lv:
            f0, f1 = lv["flash"]
            shown += [(f0 + j * 0.2, j % 2 == 1) for j in range(int(WALL_FLASH / 0.2))] + [(f1, True)]
        if "next" in lv:
            shown.append((lv["next"], False))
        out.append(f'<g fill="{wall}" opacity="0">{tl.show(shown)}{"".join(bars)}</g>')

    for n in sorted(pellets):
        x, y = cell_xy(n)
        shown = [(0, True)]
        for lv in levels:
            shown.append((lv["start"], True))
            if n in lv["game"]["eaten_at"]:
                shown.append((lv["tick"](lv["game"]["eaten_at"][n]), False))
        gone = tl.show(shown)
        if n in power:
            blink = 'dur="0.8s" values="1;0.25" calcMode="discrete" repeatCount="indefinite"'
            out.append(f'<g>{gone}<rect x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}" fill="url(#l1)"/>'
                       f'<g transform="translate({x + CELL_W // 2},{y + CELL_H // 2})">'
                       f'{pixel_art(POWER, accent, 3)}<animate attributeName="opacity" {blink}/></g></g>')
        else:
            out.append(f'<g>{gone}<rect x="{x}" y="{y}" width="{CELL_W}" height="{CELL_H}" '
                       f'fill="{fill_for(by_node[n]["level"], ink)}"/></g>')


    seen = set()
    for w, week in enumerate(weeks):
        month = next((d["date"] for d in week if d["date"].day == 1), None)
        first = week[0]["date"]
        if month is None and w == 0 and first.day <= 7:
            month = first
        if month and month.month not in seen:
            seen.add(month.month)
            out.append(f'<text x="{PAD + w * COL}" y="{grid_top + 7 * ROW + 12}" font-size="10" '
                       f'fill="{ink}" opacity="0.75">{month:%b}</text>')

    def track(get, glide=lambda f: False) -> tuple[list[float], list]:
        times, vals = [], []
        for lv in levels:
            frames = lv["game"]["frames"]
            times.append(lv["start"])
            vals.append(get(frames[0], 0))
            seq = [get(f, k) for k, f in enumerate(frames)]
            for k, f in enumerate(frames):
                if 0 < k < len(seq) - 1 and glide(f) and seq[k] == seq[k - 1] != seq[k + 1]:
                    continue
                times.append(lv["tick"](k))
                vals.append(seq[k])
            if "next" in lv:
                times.append(lv["next"] - JUMP)
                vals.append(vals[-1])
        return times, vals

    for i, fill in enumerate(GHOST_FILLS):
        def ghost_pos(f, k, i=i):
            x, y = centre(f["ghosts"][i][0])
            return x, y - 2 if f["ghosts"][i][2] and k % 4 >= 2 else y  
        times, pts = track(ghost_pos, glide=lambda f, i=i: not f["ghosts"][i][2])  
        looks = []
        for lv in levels:
            frames = lv["game"]["frames"]
            looks.append((lv["start"], frames[0]["ghosts"][i][1]))
            looks += [(lv["tick"](k), f["ghosts"][i][1]) for k, f in enumerate(frames) if k]
            if "flash" in lv:
                looks.append((lv["flash"][0], "hidden"))
        looks[0] = (0, looks[0][1])
        paint = ink if fill == "solid" else f"url(#{fill})"
        sprites = {"normal": pixel_art(GHOST, paint), "scared": pixel_art(GHOST_SCARED, wall),
                   "flash": pixel_art(GHOST_SCARED, ink), "eyes": pixel_art(GHOST_EYES, ink)}
        out.append("<g>" + tl.motion(times, pts) + "".join(
            f'<g>{art}{tl.show([(t, look == nm) for t, look in looks])}</g>' for nm, art in sprites.items()
        ) + "</g>")


    times, pac_pts = track(lambda f, k: centre(f["pac"]))
    _, pac_looks = track(lambda f, k: f["pac_look"])

    turns = [(0.0, str(ANGLE[levels[0]["game"]["frames"][0]["facing"]]))]
    for lv in levels:
        frames = lv["game"]["frames"]
        turns.append((lv["start"], str(ANGLE[frames[0]["facing"]])))
        turns += [(lv["tick"](k - 1), str(ANGLE[f["facing"]])) for k, f in enumerate(frames) if k]
    looks = list(zip([0.0] + times[1:], pac_looks))
    for lv in levels:  
        if "next" in lv:
            looks.append((lv["next"] - JUMP, "hidden"))
            looks.append((lv["next"], "alive"))
    looks.sort(key=lambda x: x[0])
    chomp = 'dur="0.36s" repeatCount="indefinite" calcMode="discrete"'
    alive = tl.show([(t, v == "alive") for t, v in looks])
    body = (f'<g>{alive}<g><animateTransform attributeName="transform" type="rotate" {tl.steps(turns)}/>'
            f'<g>{pixel_art(PACMAN_OPEN, "inherit")}<animate attributeName="opacity" values="1;0" {chomp}/></g>'
            f'<g>{pixel_art(PACMAN_SHUT, "inherit")}<animate attributeName="opacity" values="0;1" {chomp}/></g>'
            f'</g></g>')
    if any(v.startswith("die") for _, v in looks):
        body += "".join(
            f'<g opacity="0">{pixel_art(art, "inherit")}{tl.show([(t, v == f"die{j}") for t, v in looks])}</g>'
            for j, art in enumerate(PACMAN_DEATH))
    others = list(PAC_COLOURS[name])
    random.Random(seed).shuffle(others)
    colours = [accent] + others[:COLOUR_CYCLE - 1]
    recolour = (f'<animate attributeName="fill" '
                f'{tl.steps([(mt["start"], colours[m % len(colours)]) for m, mt in enumerate(matches)])}/>')
    out.append(f'<g fill="{accent}">{recolour}{tl.motion(times, pac_pts)}{body}</g>')

    
    spares = [(t, f["lives"] - 1) for t, f in zip([0.0] + times[1:], track(lambda f, k: f)[1])]
    icons = "".join(
        f'<g transform="translate({PAD + 8 + j * 18},{grid_top - 13})" opacity="0">'
        f'{tl.show([(t, n > j) for t, n in spares])}{pixel_art(PACMAN_OPEN, "inherit")}</g>'
        for j in range(LIVES - 1))
    out.append(f'<g fill="{accent}">{recolour}{icons}</g>')

  
    hx = cell_xy(min(house["cells"]))[0] + HOUSE_W * COL // 2 - 2
    hy = cell_xy(max(house["cells"]))[1] + ROW + CELL_H // 2 + 4

    def sign(text: str, fill: str, shown: list[tuple[float, bool]]) -> str:
        w = len(text) * 7.2 + 12  
        return (f'<g opacity="0">{tl.show(shown)}'
                f'<rect x="{hx - w / 2:.0f}" y="{hy - 12}" width="{w:.0f}" height="16" fill="{bg}"/>'
                f'<text x="{hx}" y="{hy}" text-anchor="middle" font-size="12" font-weight="bold" '
                f'fill="{fill}">{text}</text></g>')

    ready = [(0, True)]
    for lv in levels:
        ready += [(lv["start"], True), (lv["play"], False)]
        ready += [(lv["tick"](k), f["sign"] == "READY!") for k, f in enumerate(lv["game"]["frames"]) if k]
        out.append(f'<text x="{PAD + grid_w}" y="{grid_top - 9}" text-anchor="end" font-size="11" '
                   f'font-weight="bold" fill="{ink}" opacity="0">LEVEL {lv["number"]}'
                   f'{tl.show([(0, lv is levels[0]), (lv["start"], True), (lv["stop"], lv is levels[-1])])}</text>')
        if "flash" in lv and not lv["last"]:
            out.append(sign(f"LEVEL {lv['number']} CLEAR!", accent, [(0, False), (lv["flash"][0], True), (lv["next"], False)]))
    out.append(sign("READY!", accent, ready))

    for m, match in enumerate(matches):
        last_match = m == len(matches) - 1
        result, colour = {"over": ("GAME OVER", ink), "time": ("TIME UP", ink),
                          "clear": ("YOU WIN!", accent)}[match["outcome"]]
        out.append(sign(result, colour, [(0, False), (match["result_at"], True), (match["end"], last_match)]))
        span = [(0, m == 0), (match["start"], True), (match["end"], last_match)]
        # His danger memory: small marks on the days he now steers clear of.
        spots = [n for n, w in match["memory"].items() if w >= 1.5 and n in by_node and n not in house["cells"]]
        if spots:
            marks = "".join(f'<g transform="translate({centre(n)[0]},{centre(n)[1]})">'
                            f'{pixel_art(DANGER_MARK, accent, 1)}</g>' for n in sorted(spots))
            out.append(f'<g opacity="0">{tl.show(span)}<g opacity="0.8">{marks}</g></g>')


    events = [(0.0, 0, "match")]
    for m, match in enumerate(matches):
        if m:
            events.append((match["start"], m, "match"))
        if match["outcome"] == "clear":
            events.append((match["result_at"], m, "win"))
    for lv in levels:
        frames = lv["game"]["frames"]
        events += [(lv["tick"](k), lv["match"], "death") for k, f in enumerate(frames)
                   if f["pac_look"] == "die0" and (k == 0 or frames[k - 1]["pac_look"] != "die0")]
    events.sort(key=lambda e: e[0])
    states, deaths, wins = [], 0, 0
    for t, m, kind in events:
        deaths += kind == "death"
        wins += kind == "win"
        if states and states[-1][0] == t:
            states.pop()
        states.append((t, m, deaths, wins))
    for i, (t, m, d, w) in enumerate(states):
        until = states[i + 1][0] if i + 1 < len(states) else dur
        last = i + 1 == len(states)
        out.append(f'<text x="{PAD + 8 + (LIVES - 1) * 18 + 4}" y="{grid_top - 9}" font-size="11" '
                   f'font-weight="bold" fill="{ink}" opacity="0">MATCH {m + 1} &#183; {d} - Deaths &#183; Won: {w}'
                   f'{tl.show([(0, i == 0), (t, True), (until, last)])}</text>')

    out.append("</svg>")
    for m, match in enumerate(matches):
        runs = ", ".join(f"L{lv['number']} {lv['game']['outcome']} ({len(lv['game']['eaten_at'])} eaten, "
                         f"{lv['game']['ghosts_eaten']} ghosts, {lv['game']['deaths']} lives lost)"
                         for lv in match["levels"])
        print(f"{name} match {m + 1} {match['policy']}: {runs}")
    print(f"{name}: loop {dur:.0f}s, colours {colours[:len(matches)]}")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use a fake calendar")
    ap.add_argument("--seed", type=int, help="override the daily maze/game seed")
    args = ap.parse_args()
    today = datetime.now(TZ).date()

    if args.offline:
        weeks = fake_calendar(today)
    else:
        try:
            weeks = fetch_public_calendar()
        except Exception as err:  # page layout changed: fall back to the API
            print("public calendar failed, using API:", err)
            weeks = fetch_api_calendar(os.environ.get("ACCESS_TOKEN") or os.environ["GITHUB_TOKEN"])
    stats = tiles(weeks, today)
    print("tiles:", stats)

    if args.seed is not None:
        seed, data = args.seed, learn(weeks, args.seed)
    else:
        seed, data = pick_run(weeks, today.toordinal())
    for name, theme in THEMES.items():
        path = ROOT / f"pacman_{name}.svg"
        path.write_text(render(name, theme, weeks, stats, seed, data), encoding="utf-8")
        print("wrote", path.name, f"({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
