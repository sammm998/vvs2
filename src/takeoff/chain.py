"""Sammanfogning av rorgeometri, med plataatest i stallet for gissad troskel.

Ritade rorlinjer bryts dar symboler, beteckningar och korsande ledningar
ligger over dem. Ett verkligt ror ar sammanhangande. Sammanfogningen bygger
darfor broar over glapp - men hur stort glapp som far overbryggas ar
ritningsberoende och far inte gissas.

Metoden: svep troskeln over ett intervall, mat totallangden vid varje steg,
och lagg troskeln mitt i den *plataa* dar totalen ar okanslig for troskeln.
Finns ingen plataa ar sammanfogningen inte tillforlitlig pa den ritningen,
och det flaggas i stallet for att gissas.

Trosklarna uttrycks i multiplar av rorstilens egen medianlinjebredd (R1).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .extract import PathRecord, Sheet, corner_split

Point = tuple[float, float]
Run = list[Point]


@dataclass
class Bridge:
    a: int
    b: int
    gap: float


@dataclass
class ChainResult:
    runs: list[Run]
    threshold: float
    plateau_width: float
    unit: str
    sweep: list[tuple[float, float]]
    flags: list[str] = field(default_factory=list)
    bridged: int = 0
    bridged_length: float = 0.0

    @property
    def total_length(self) -> float:
        return sum(_polyline_length(r) for r in self.runs)

    def as_dict(self) -> dict:
        return {
            "value": round(self.threshold, 4),
            "plateau_width": round(self.plateau_width, 4),
            "unit": self.unit,
            "bridged": self.bridged,
            "bridged_length_pt": round(self.bridged_length, 1),
            "flags": self.flags,
        }


def _polyline_length(r: Run) -> float:
    return sum(math.dist(r[i], r[i + 1]) for i in range(len(r) - 1))


def straight_runs(paths: list[PathRecord]) -> list[Run]:
    """Dela banorna i raka delkedjor vid verkliga horn."""
    runs: list[Run] = []
    for p in paths:
        for chain in corner_split(p):
            if not chain:
                continue
            pts: Run = [chain[0][0]]
            for a, b in chain:
                if math.dist(pts[-1], a) > 1e-9:
                    pts.append(a)
                pts.append(b)
            if _polyline_length(pts) > 0:
                runs.append(pts)
    return runs


def _direction(r: Run) -> float:
    a, b = r[0], r[-1]
    return math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi


def _join(runs: list[Run], gap: float, angle_tol: float, offset_tol: float) -> tuple[list[Run], list[Bridge]]:
    """Bygg broar mellan raka kedjor som fortsatter i varandra.

    Varje ande far hogst en bro, sa att ett ror inte kan grena sig genom
    sammanfogning. Broar valjs i vaxande glappordning.
    """
    ends: list[tuple[int, int, Point]] = []
    for i, r in enumerate(runs):
        ends.append((i, 0, r[0]))
        ends.append((i, 1, r[-1]))

    cell = max(gap, 1e-6)
    grid: dict[tuple[int, int], list[int]] = {}
    for k, (_, _, p) in enumerate(ends):
        grid.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(k)

    cand: list[tuple[float, int, int]] = []
    for k, (ri, side, p) in enumerate(ends):
        gx, gy = int(p[0] // cell), int(p[1] // cell)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for m in grid.get((gx + i, gy + j), ()):
                    if m <= k:
                        continue
                    rj, side2, q = ends[m]
                    if rj == ri:
                        continue
                    d = math.dist(p, q)
                    if d > gap:
                        continue
                    da = abs(_direction(runs[ri]) - _direction(runs[rj]))
                    da = min(da, math.pi - da)
                    if da > angle_tol:
                        continue
                    if _lateral_offset(runs[ri], q) > offset_tol:
                        continue
                    cand.append((d, k, m))
    cand.sort()

    used: set[int] = set()
    parent = list(range(len(runs)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    bridges: list[Bridge] = []
    adj: dict[int, list[tuple[int, float]]] = {}
    for d, k, m in cand:
        if k in used or m in used:
            continue
        ri, rj = ends[k][0], ends[m][0]
        if find(ri) == find(rj):
            continue
        used.add(k)
        used.add(m)
        parent[find(ri)] = find(rj)
        bridges.append(Bridge(k, m, d))
        adj.setdefault(k, []).append((m, d))
        adj.setdefault(m, []).append((k, d))

    merged = _assemble(runs, ends, adj)
    return merged, bridges


def _lateral_offset(run: Run, q: Point) -> float:
    """Vinkelratt avstand fran ``q`` till kedjans forlangda linje."""
    a, b = run[0], run[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    if n <= 0:
        return math.dist(a, q)
    return abs((q[0] - a[0]) * dy - (q[1] - a[1]) * dx) / n


def _assemble(runs: list[Run], ends, adj) -> list[Run]:
    """Foljer broarna och satter ihop kedjorna till polylinjer.

    Varje ande har hogst en bro, sa strukturen ar en samling oppna kedjor och
    slutna slingor. Oppna kedjor gas fran sin fria ande; slingor bryts pa
    godtycklig plats.
    """
    end_index: dict[tuple[int, int], int] = {(ends[k][0], ends[k][1]): k for k in range(len(ends))}
    partner: dict[int, int] = {k: lst[0][0] for k, lst in adj.items() if lst}
    visited = [False] * len(runs)
    out: list[Run] = []

    def walk(start_run: int, enter_side: int) -> Run:
        poly: Run = []
        cur, side = start_run, enter_side
        while not visited[cur]:
            visited[cur] = True
            poly.extend(runs[cur] if side == 0 else runs[cur][::-1])
            nxt = partner.get(end_index[(cur, 1 - side)])
            if nxt is None:
                break
            nid, nside, _ = ends[nxt]
            if visited[nid]:
                break
            cur, side = nid, nside
        return poly

    for r in range(len(runs)):
        if visited[r]:
            continue
        free = next((s for s in (0, 1) if end_index[(r, s)] not in partner), None)
        if free is not None:
            out.append(walk(r, free))
    for r in range(len(runs)):  # kvarvarande slingor
        if not visited[r]:
            out.append(walk(r, 0))
    return out


def sweep(
    runs: list[Run],
    unit: float,
    steps: int = 40,
    max_multiple: float = 12.0,
    angle_tol: float = math.radians(2.0),
) -> list[tuple[float, float]]:
    """Totallangd som funktion av sammanfogningstroskeln."""
    out = []
    for i in range(steps + 1):
        t = max_multiple * unit * i / steps
        merged, bridges = _join(runs, t, angle_tol, unit * 0.5)
        total = sum(_polyline_length(r) for r in runs) + sum(b.gap for b in bridges)
        out.append((t / unit, total))
    return out


def find_plateau(curve: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Hitta det plana partiet i sveptkurvan.

    Returnerar (troskel i enheter, plataans bredd, relativ lutning dar).
    Plataan definieras som det langsta sammanhangande intervall dar den
    relativa forandringen per steg understiger medianforandringen.
    """
    if len(curve) < 4:
        return (0.0, 0.0, 0.0)
    deltas = []
    for i in range(1, len(curve)):
        prev = curve[i - 1][1] or 1.0
        deltas.append(abs(curve[i][1] - prev) / prev)
    med = statistics.median(deltas) or 1e-9
    flat = [d <= med for d in deltas]
    best_len, best_start = 0, 0
    cur_len, cur_start = 0, 0
    for i, f in enumerate(flat):
        if f:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len, best_start = cur_len, cur_start
        else:
            cur_len = 0
    if best_len == 0:
        return (curve[len(curve) // 2][0], 0.0, med)
    lo = curve[best_start][0]
    hi = curve[min(len(curve) - 1, best_start + best_len)][0]
    return ((lo + hi) / 2, hi - lo, med)


def build(sheet: Sheet, paths: list[PathRecord], unit: float | None = None) -> ChainResult:
    runs = straight_runs(paths)
    if unit is None:
        widths = [p.width for p in paths if p.width > 0]
        unit = statistics.median(widths) if widths else sheet.epsilon()
    curve = sweep(runs, unit)
    thr_units, plateau, _ = find_plateau(curve)
    flags: list[str] = []
    if plateau <= 0:
        flags.append("chain:no_plateau")
    merged, bridges = _join(runs, thr_units * unit, math.radians(2.0), unit * 0.5)
    return ChainResult(
        runs=merged,
        threshold=thr_units,
        plateau_width=plateau,
        unit="median_pipe_width",
        sweep=curve,
        flags=flags,
        bridged=len(bridges),
        bridged_length=sum(b.gap for b in bridges),
    )
