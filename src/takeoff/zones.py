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

    Zonen harleds ur ritningens egen geometri: ett kluster av langa,
    parallella, osammanhangande linjer. Inga fasta koordinater (CLAUDE.md,
    avsnitt Forbjudet).

    Langden i zonen tas ALDRIG bort tyst - den redovisas som egen rad (R10).
    """

    def __init__(self, cells: set[tuple[int, int]], cell: float, clusters: list[str]):
        self.cells = cells
        self.cell = cell
        self.clusters = clusters

    def __bool__(self) -> bool:
        return bool(self.cells)

    def contains(self, point) -> bool:
        if not self.cells:
            return False
        return (int(point[0] // self.cell), int(point[1] // self.cell)) in self.cells

    def as_dict(self) -> dict:
        return {"cells": len(self.cells), "cell_pt": round(self.cell, 2), "clusters": self.clusters}


def hatch_mask(sheet, style_index, selection, zonemap, cell_factor: float = 6.0) -> HatchMask:
    from .styles import angular_concentration

    pipe_ids = set(selection.pipe_clusters)
    by_id = {p.id: p for p in sheet.paths}
    cell = max(sheet.median_width() * cell_factor, 1e-6)
    chosen: list[str] = []
    cells: set[tuple[int, int]] = set()
    for c in style_index.clusters:
        if c.id in pipe_ids or c.n_paths < 20 or c.total_length <= 0:
            continue
        # Schraffering: enriktad, langa banor, och banorna mots inte - de ar
        # parallella streck, inte ett nat.
        if angular_concentration(c) <= 0.8 or c.connectivity >= 0.10:
            continue
        if zonemap.classify(c.bbox) != "plan":
            continue
        chosen.append(c.id)
        for pid in c.path_ids:
            for a, b in by_id[pid].segments:
                n = max(1, int(math.dist(a, b) / cell))
                for k in range(n + 1):
                    t = k / n
                    px = a[0] + (b[0] - a[0]) * t
                    py = a[1] + (b[1] - a[1]) * t
                    cells.add((int(px // cell), int(py // cell)))
    return HatchMask(cells, cell, chosen)
