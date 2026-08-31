"""Zoner: planyta, ram, teckenforklaring, titelfalt, detaljrutor.

Zoner harleds topologiskt ur ritningens egen geometri. Hardkodade koordinater
ar forbjudna (CLAUDE.md, avsnitt Forbjudet).

Metod:
1. Ramen ar den storsta slutna rektangeln som taxker en stor del av arket.
2. Paneler ar slutna rektanglar innanfor ramen som ror ramens kant. Titelfalt,
   teckenforklaring och detaljrutor ar alla paneler.
3. Planytan ar den storsta rektangel innanfor ramen som inte overlappar nagon
   panel. Den hittas med storsta-rektangel-i-histogram over ett rutnat.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field

from .extract import Sheet

Box = tuple[float, float, float, float]

# En ytschraffering ar per definition en FAMILJ av manga linjer. Ett tjugotal
# parallella vaggkonturer ar inte en schrafferad yta. Antal, inte matt (R1).
MIN_HATCH_PATHS = 60

# Andel grannlinjer som maste ligga pa samma delning for att monstret ska
# raknas som regelbundet. Dimensionslos andel (R1).
MIN_HATCH_REGULARITY = 0.80


@dataclass
class Zone:
    name: str
    box: Box
    kind: str
    detail: dict = field(default_factory=dict)

    def contains(self, box: Box, frac: float = 0.6) -> bool:
        return _overlap_fraction(box, self.box) >= frac


@dataclass
class ZoneMap:
    frame: Box
    plan: Box
    zones: list[Zone]

    @property
    def excluded(self) -> list[Zone]:
        return [z for z in self.zones if z.kind != "plan"]

    def classify(self, box: Box) -> str:
        if _overlap_fraction(box, self.plan) >= 0.6:
            for z in self.excluded:
                if z.contains(box):
                    return z.kind
            return "plan"
        for z in self.excluded:
            if z.contains(box):
                return z.kind
        return "frame"

    def as_dict(self) -> dict:
        return {
            "frame": [round(v, 1) for v in self.frame],
            "plan": [round(v, 1) for v in self.plan],
            "zones": [
                {"name": z.name, "kind": z.kind, "box": [round(v, 1) for v in z.box], **z.detail}
                for z in self.zones
            ],
        }


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersect(a: Box, b: Box) -> Box:
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def _overlap_fraction(inner: Box, outer: Box) -> float:
    a = _area(inner)
    if a <= 0:
        # Degenererad bana: falla tillbaka pa mittpunkten.
        cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
        return 1.0 if outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3] else 0.0
    return _area(_intersect(inner, outer)) / a


def _is_rectangular(path) -> bool:
    """Banan ar en axelriktad rektangel (fyra ortogonala segment)."""
    segs = [s for s in path.segments if s[0] != s[1]]
    if not 3 <= len(segs) <= 8:
        return False
    x0, y0, x1, y1 = path.bbox
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return False
    tol = min(x1 - x0, y1 - y0) * 0.02
    for a, b in segs:
        if abs(a[0] - b[0]) > tol and abs(a[1] - b[1]) > tol:
            return False
    return True


def detect(sheet: Sheet) -> ZoneMap:
    tf = sheet.transform
    page: Box = (0.0, 0.0, tf.width, tf.height)
    page_area = _area(page)

    rects = [p for p in sheet.paths if _is_rectangular(p)]

    # 1. Ramen
    frame = page
    best = 0.0
    for p in rects:
        a = _area(p.bbox)
        if 0.30 * page_area <= a <= 0.995 * page_area and a > best:
            best, frame = a, p.bbox
    frame_area = _area(frame)

    # 2. Paneler: inramade rutor innanfor ramen. En panel ror antingen ramens
    #    kant (titelfalt, revideringslista) eller ar innehallstat jamfort med
    #    ritningen i ovrigt (detaljruta, teckenforklaring). Tatheten mats mot
    #    sidans egen medeltathet - relativt matt, ingen konstant (R1).
    edge_tol = max(frame[2] - frame[0], frame[3] - frame[1]) * 0.02
    mean_density = len(sheet.paths) / max(frame_area / 10000.0, 1e-9)
    candidates: list[Box] = []
    for p in rects:
        b = p.bbox
        a = _area(b)
        if a < frame_area * 0.004 or a > frame_area * 0.6:
            continue
        if _overlap_fraction(b, frame) < 0.9:
            continue
        touches = (
            abs(b[0] - frame[0]) < edge_tol
            or abs(b[2] - frame[2]) < edge_tol
            or abs(b[1] - frame[1]) < edge_tol
            or abs(b[3] - frame[3]) < edge_tol
        )
        if touches or _density(sheet, b) > mean_density * 2.0:
            candidates.append(b)
    panels = _merge_boxes(candidates)

    # 3. Planytan: storsta panelfria rektangeln innanfor ramen
    plan = _largest_free_rect(frame, panels)

    zones = [Zone("plan", plan, "plan")]
    density = _text_density(sheet, panels)
    for i, b in enumerate(sorted(panels, key=lambda z: -_area(z))):
        kind = _panel_kind(b, frame, density.get(b, 0.0))
        zones.append(Zone(f"panel{i}", b, kind, {"glyph_density": round(density.get(b, 0.0), 4)}))
    return ZoneMap(frame=frame, plan=plan, zones=zones)


def _panel_kind(b: Box, frame: Box, density: float) -> str:
    fw, fh = frame[2] - frame[0], frame[3] - frame[1]
    right = (b[0] - frame[0]) / fw > 0.66
    bottom = (b[1] - frame[1]) / fh > 0.66
    tall = (b[3] - b[1]) / max(b[2] - b[0], 1e-9) > 1.2
    if right and bottom:
        return "titleblock"
    if right and (tall or density > 0.5):
        return "legend"
    return "detail"


def _density(sheet: Sheet, b: Box) -> float:
    """Banor per 10 000 kvadratpunkter innanfor ``b``."""
    a = _area(b)
    if a <= 0:
        return 0.0
    n = sum(1 for p in sheet.paths if _overlap_fraction(p.bbox, b) > 0.9)
    return n / (a / 10000.0)


def _text_density(sheet: Sheet, panels: list[Box]) -> dict[Box, float]:
    return {b: _density(sheet, b) for b in panels}


def _merge_boxes(boxes: list[Box], iterations: int = 3) -> list[Box]:
    """Sla ihop rektanglar som overlappar kraftigt (nastlade ramar)."""
    cur = list(boxes)
    for _ in range(iterations):
        merged: list[Box] = []
        used = [False] * len(cur)
        for i, a in enumerate(cur):
            if used[i]:
                continue
            acc = a
            for j in range(i + 1, len(cur)):
                if used[j]:
                    continue
                b = cur[j]
                inter = _area(_intersect(acc, b))
                if inter > 0.5 * min(_area(acc), _area(b)):
                    acc = (min(acc[0], b[0]), min(acc[1], b[1]), max(acc[2], b[2]), max(acc[3], b[3]))
                    used[j] = True
            merged.append(acc)
            used[i] = True
        if len(merged) == len(cur):
            return merged
        cur = merged
    return cur


def _largest_free_rect(frame: Box, panels: list[Box], nx: int = 240, ny: int = 170) -> Box:
    fx0, fy0, fx1, fy1 = frame
    w, h = fx1 - fx0, fy1 - fy0
    if w <= 0 or h <= 0:
        return frame
    cw, ch = w / nx, h / ny
    blocked = [[False] * nx for _ in range(ny)]
    for b in panels:
        i0 = max(0, int((b[0] - fx0) / cw))
        i1 = min(nx - 1, int((b[2] - fx0) / cw))
        j0 = max(0, int((b[1] - fy0) / ch))
        j1 = min(ny - 1, int((b[3] - fy0) / ch))
        for j in range(j0, j1 + 1):
            row = blocked[j]
            for i in range(i0, i1 + 1):
                row[i] = True

    heights = [0] * nx
    best = (0, 0, 0, 0, 0)  # area, i0, j0, i1, j1
    for j in range(ny):
        for i in range(nx):
            heights[i] = 0 if blocked[j][i] else heights[i] + 1
        stack: list[tuple[int, int]] = []
        for i in range(nx + 1):
            cur = heights[i] if i < nx else 0
            start = i
            while stack and stack[-1][1] >= cur:
                s, hgt = stack.pop()
                area = hgt * (i - s)
                if area > best[0]:
                    best = (area, s, j - hgt + 1, i - 1, j)
                start = s
            stack.append((start, cur))
    if best[0] == 0:
        return frame
    _, i0, j0, i1, j1 = best
    return (fx0 + i0 * cw, fy0 + j0 * ch, fx0 + (i1 + 1) * cw, fy0 + (j1 + 1) * ch)


# --------------------------------------------------------------------------
# Maskade zoner (fas 4)


class HatchMask:
    """Schrafferad zon: omrade som ritningen sjalv markerar som undantaget.

    Schraffering over ett planomrade betyder normalt att omradet ligger
    utanfor det som ritningen redovisar - annan entreprenad, annan etapp,
    eller en angransande ritning. Ledningar ritas ofta igenom zonen for att
    visa anslutningen, men de ingar inte i mangden.

    Zonen harleds ur ritningens egen geometri. Rutnatets cell ar
    schrafferingens EGEN linjedelning: da hamnar tva grannlinjer i
    angransande celler och ytan mellan dem sluts, i stallet for att lamna
    springor dar ett ror kan lopa omaskerat. Delningen mats per kluster - en
    grov och en fin schraffering pa samma ritning far var sin cell.

    Langden i zonen tas ALDRIG bort tyst - den redovisas som egen rad (R10).
    """

    def __init__(self, regions: list[tuple[float, set[tuple[int, int]]]], clusters: list[str]):
        self.regions = regions
        self.clusters = clusters

    def __bool__(self) -> bool:
        return any(cells for _, cells in self.regions)

    @property
    def cell(self) -> float:
        return self.regions[0][0] if self.regions else 0.0

    @property
    def cells(self) -> set[tuple[int, int]]:
        out: set[tuple[int, int]] = set()
        for _, c in self.regions:
            out |= c
        return out

    def contains(self, point) -> bool:
        for cell, cells in self.regions:
            if cells and (int(point[0] // cell), int(point[1] // cell)) in cells:
                return True
        return False

    def as_dict(self) -> dict:
        return {
            "clusters": self.clusters,
            "regions": [
                {"cell_pt": round(c, 2), "cells": len(cs)} for c, cs in self.regions
            ],
        }


def _hatch_pitch(cluster, by_id) -> tuple[float, float]:
    """Schrafferingens linjedelning och hur REGELBUNDEN den ar.

    Mats vinkelratt mot klustrets dominerande riktning. Returnerar
    (delning, andel grannavstand som delar den delningen).

    Regelbundenheten ar det som definierar en schraffering. Ett
    vaggunderlag har ocksa parallella linjer i en huvudriktning, men deras
    avstand ar godtyckliga: rummen ar olika stora. Pa 0011 delar 61 % av
    schrafferingens grannavstand samma delning, mot 6 % for underlaget.
    """
    segs = []
    for pid in cluster.path_ids:
        for a, b in by_id[pid].segments:
            if math.dist(a, b) > 0:
                segs.append((a, math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi))
    if not segs:
        return (0.0, 0.0)
    dominant = collections.Counter(round(ang, 2) for _, ang in segs).most_common(1)[0][0]
    nx, ny = -math.sin(dominant), math.cos(dominant)
    proj = sorted({round(a[0] * nx + a[1] * ny, 1) for a, ang in segs if abs(ang - dominant) < 0.03})
    gaps = [round(proj[i + 1] - proj[i], 1) for i in range(len(proj) - 1)]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return (0.0, 0.0)
    pitch, n = collections.Counter(gaps).most_common(1)[0]
    return (pitch, n / len(gaps))


def _parallel_pitch(cluster, by_id) -> tuple[float, float]:
    """Delningen mellan parallella grannlinjer, och hur regelbunden den ar.

    For varje linje soks narmaste parallella granne som overlappar den i
    langdled. Returnerar (typisk delning, andel grannar pa den delningen).

    Det ar detta som DEFINIERAR en schraffering: parallella linjer pa
    regelbundet avstand. Matt lokalt, granne mot granne, sa att det inte
    spelar nagon roll om schrafferingen ligger som ett block eller som en
    ram runt planet. Ett bbox-baserat matt klarar det forsta men inte det
    andra.
    """
    lines = []
    for pid in cluster.path_ids:
        for a, b in by_id[pid].segments:
            if math.dist(a, b) > 0:
                lines.append((a, b, math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi))
    if len(lines) < 20:
        return (0.0, 0.0)
    dominant = collections.Counter(round(ang, 2) for _, _, ang in lines).most_common(1)[0][0]
    sel = [
        (a, b) for a, b, ang in lines
        if min(abs(ang - dominant), math.pi - abs(ang - dominant)) < 0.05
    ]
    if len(sel) < 20:
        return (0.0, 0.0)
    nx, ny = -math.sin(dominant), math.cos(dominant)
    tx, ty = math.cos(dominant), math.sin(dominant)
    items = sorted(
        (
            a[0] * nx + a[1] * ny,
            min(a[0] * tx + a[1] * ty, b[0] * tx + b[1] * ty),
            max(a[0] * tx + a[1] * ty, b[0] * tx + b[1] * ty),
        )
        for a, b in sel
    )
    neighbours = []
    for i, (p0, s0, e0) in enumerate(items):
        for j in range(i + 1, len(items)):
            p1, s1, e1 = items[j]
            gap = p1 - p0
            if gap <= 0.05:
                continue
            if min(e0, e1) - max(s0, s1) > 0.3 * min(e0 - s0, e1 - s1):
                neighbours.append(gap)
                break
    if len(neighbours) < 10:
        return (0.0, 0.0)
    pitch = collections.Counter(round(d, 1) for d in neighbours).most_common(1)[0][0]
    regular = sum(1 for d in neighbours if abs(d - pitch) <= pitch * 0.15) / len(neighbours)
    return (pitch, regular)


def _covered_cells(cluster, by_id, cell: float) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for pid in cluster.path_ids:
        for a, b in by_id[pid].segments:
            n = max(1, int(math.dist(a, b) / cell))
            for k in range(n + 1):
                t = k / n
                cells.add((int((a[0] + (b[0] - a[0]) * t) // cell),
                           int((a[1] + (b[1] - a[1]) * t) // cell)))
    return cells


def hatch_mask(sheet, style_index, selection, zonemap, cell_factor: float = 6.0) -> HatchMask:
    """Harled ritningens maskade zoner ur dess egen schraffering.

    En schrafferad yta i planet betyder normalt att omradet ligger utanfor det
    ritningen redovisar - annan entreprenad, annan etapp, eller en angransande
    ritning. Ledningar ritas ofta igenom zonen for att visa anslutningen, men
    de ingar inte i mangden.

    Tre villkor, alla relativa till ritningen sjalv (R1):

    1. REGELBUNDNA parallella grannar. Det ar definitionen av en
       schraffering, och den haller oavsett om monstret ligger som ett block
       eller som en ram runt planet.
    2. FIN delning - hogst en hundradel av arkets diagonal. En schraffering ar
       en ritteknisk fyllning; ett modulnat eller en rumsindelning har
       delningar i byggnadsmatt och faller bort har.
    3. STOR plantackning, som utstickare. Ett dorrslag och en trappa ar ocksa
       regelbundna och finmaskiga, men de tacker en brakdel av planet.
       Schrafferingen tacker 10-26 %, ovriga kandidater under 1 %.
    """
    pipe_ids = set(selection.pipe_clusters)
    by_id = {p.id: p for p in sheet.paths}
    disqualified = {"text_or_glyph", "frame", "degenerate"}
    max_pitch = sheet.transform.diagonal * 0.01
    plan = zonemap.plan
    plan_area = max((plan[2] - plan[0]) * (plan[3] - plan[1]), 1e-9)

    candidates = []
    for c in style_index.clusters:
        if c.id in pipe_ids or c.n_paths < MIN_HATCH_PATHS or c.total_length <= 0:
            continue
        if zonemap.classify(c.bbox) != "plan":
            continue
        if selection.reasons.get(c.id) in disqualified:
            continue
        pitch, regular = _parallel_pitch(c, by_id)
        if pitch <= 0 or pitch > max_pitch or regular < MIN_HATCH_REGULARITY:
            continue
        cells = _covered_cells(c, by_id, max(pitch, 1e-6))
        coverage = len(cells) * pitch * pitch / plan_area
        candidates.append((c, pitch, coverage))

    if not candidates:
        return HatchMask([], [])

    # Schrafferingen ar utstickaren i plantackning. Att jamfora mot en median
    # ar sprott nar kandidaterna ar fa; utstickaren ar stabil.
    top = max(cov for _, _, cov in candidates)
    cutoff = top * 0.5

    chosen: list[str] = []
    regions: list[tuple[float, set[tuple[int, int]]]] = []
    for c, pitch, coverage in candidates:
        if coverage < cutoff:
            continue
        chosen.append(c.id)
        # Finmaskigt rutnat for skarp zonkant, och en slutning som ar exakt
        # sa bred som schrafferingens egen delning. Da sluts ytan MELLAN
        # linjerna - dar ett ror annars loper omaskerat - utan att zonen
        # svaller ut over sin verkliga kant.
        cell = max(sheet.median_width() * cell_factor, 1e-6)
        radius = max(1, math.ceil(pitch / cell / 2))
        seed = _covered_cells(c, by_id, cell)
        cells = {
            (x + dx, y + dy)
            for (x, y) in seed
            for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)
        }
        regions.append((cell, cells))
    return HatchMask(regions, chosen)
