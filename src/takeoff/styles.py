"""R7 - stil fore geometri.

Enskilda banor klassificeras aldrig. Alla banor grupperas forst i stilkluster
pa (farg, linjebredd, strecksignatur, lager, sluten). Klustret ar sedan
enheten som klassificeras.

Varje bana hamnar i exakt ett kluster (R6). Det ar ett assert, inte en
forhoppning.
"""

from __future__ import annotations

import collections
import math
import statistics
from dataclasses import dataclass, field

from .extract import PathRecord, Sheet

# --------------------------------------------------------------------------
# Fargkvantisering


def _srgb_to_lab(c: tuple[float, float, float]) -> tuple[float, float, float]:
    def lin(u: float) -> float:
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(max(0.0, min(1.0, v))) for v in c)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(a, b) -> float:
    return math.dist(a, b)


class ColorQuantizer:
    """Slar ihop farger vars delta-E understiger ``tol`` (default 5)."""

    def __init__(self, tol: float = 5.0):
        self.tol = tol
        self._reps: list[tuple[tuple[float, float, float], int]] = []

    def key(self, c: tuple[float, float, float] | None) -> int | None:
        if c is None:
            return None
        lab = _srgb_to_lab(c)
        for rep, idx in self._reps:
            if _delta_e(lab, rep) < self.tol:
                return idx
        idx = len(self._reps)
        self._reps.append((lab, idx))
        return idx

    def representative(self, idx: int | None) -> tuple[float, float, float] | None:
        if idx is None:
            return None
        return self._reps[idx][0]


def width_buckets(widths: list[float], rel_tol: float = 0.05) -> list[float]:
    """Bucketgranser for linjebredd.

    Distinkta bredder slas ihop nar det relativa avstandet understiger
    ``rel_tol``. Relativt matt, ingen pt-konstant (R1).
    """
    uniq = sorted({round(w, 4) for w in widths})
    if not uniq:
        return []
    reps = [uniq[0]]
    for w in uniq[1:]:
        ref = reps[-1]
        if ref <= 0:
            if w > 0:
                reps.append(w)
            continue
        if (w - ref) / ref > rel_tol:
            reps.append(w)
    return reps


def _bucket(w: float, reps: list[float]) -> int:
    best, bi = float("inf"), 0
    for i, r in enumerate(reps):
        d = abs(w - r) / max(r, 1e-6) if r > 0 else abs(w - r)
        if d < best:
            best, bi = d, i
    return bi


# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StyleKey:
    stroke: int | None
    fill: int | None
    width_bucket: int
    dash: str
    layer: str | None
    closed: bool

    def label(self, reps: list[float]) -> str:
        w = reps[self.width_bucket] if self.width_bucket < len(reps) else 0.0
        return f"{self.layer or '-'}|w{w:.2f}|{self.dash}|s{self.stroke}|f{self.fill}"


@dataclass
class StyleCluster:
    id: str
    key: StyleKey
    path_ids: list[int] = field(default_factory=list)
    width: float = 0.0
    cls: str = "unknown"
    confidence: float = 0.0

    # statistik, fylls av analyse()
    n_paths: int = 0
    total_length: float = 0.0
    share: float = 0.0
    angle_histogram: dict[str, float] = field(default_factory=dict)
    length_p50: float = 0.0
    length_p90: float = 0.0
    spatial_spread: float = 0.0
    connectivity: float = 0.0
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.cls,
            "confidence": round(self.confidence, 3),
            "layer": self.key.layer,
            "width": round(self.width, 3),
            "dash": self.key.dash,
            "closed": self.key.closed,
            "n_paths": self.n_paths,
            "total_length_pt": round(self.total_length, 1),
            "share": round(self.share, 4),
            "angle_histogram": {k: round(v, 3) for k, v in self.angle_histogram.items()},
            "length_p50": round(self.length_p50, 2),
            "length_p90": round(self.length_p90, 2),
            "spatial_spread": round(self.spatial_spread, 4),
            "connectivity": round(self.connectivity, 3),
        }


@dataclass
class StyleIndex:
    clusters: list[StyleCluster]
    width_reps: list[float]
    by_path: dict[int, str]

    def get(self, cid: str) -> StyleCluster:
        for c in self.clusters:
            if c.id == cid:
                return c
        raise KeyError(cid)

    def of_path(self, pid: int) -> StyleCluster:
        return self.get(self.by_path[pid])


def build(sheet: Sheet, color_tol: float = 5.0, width_rel_tol: float = 0.05) -> StyleIndex:
    q = ColorQuantizer(color_tol)
    reps = width_buckets([p.width for p in sheet.paths], width_rel_tol)
    groups: dict[StyleKey, list[int]] = collections.defaultdict(list)
    for p in sheet.paths:
        key = StyleKey(
            stroke=q.key(p.stroke) if p.kind in ("s", "fs") else None,
            fill=q.key(p.fill) if p.kind in ("f", "fs") else None,
            width_bucket=_bucket(p.width, reps) if reps else 0,
            dash=p.dash_signature,
            layer=p.layer,
            closed=p.closed,
        )
        groups[key].append(p.id)

    total_len = sum(p.length for p in sheet.paths) or 1.0
    by_id = {p.id: p for p in sheet.paths}
    clusters: list[StyleCluster] = []
    order = sorted(groups, key=lambda k: -sum(by_id[i].length for i in groups[k]))
    for n, key in enumerate(order):
        c = StyleCluster(
            id=f"c{n:03d}",
            key=key,
            path_ids=groups[key],
            width=reps[key.width_bucket] if reps else 0.0,
        )
        _analyse(c, by_id, total_len, sheet)
        clusters.append(c)

    by_path = {pid: c.id for c in clusters for pid in c.path_ids}
    assert len(by_path) == len(sheet.paths), (
        f"R6: {len(by_path)} banor klustrade av {len(sheet.paths)}"
    )
    return StyleIndex(clusters=clusters, width_reps=reps, by_path=by_path)


def _analyse(c: StyleCluster, by_id: dict[int, PathRecord], total_len: float, sheet: Sheet) -> None:
    paths = [by_id[i] for i in c.path_ids]
    lens = [p.length for p in paths]
    c.n_paths = len(paths)
    c.total_length = sum(lens)
    c.share = c.total_length / total_len
    nz = sorted(x for x in lens if x > 0)
    if nz:
        c.length_p50 = nz[len(nz) // 2]
        c.length_p90 = nz[min(len(nz) - 1, int(len(nz) * 0.9))]

    # Vinkelhistogram, langdviktat, 12 fack over [0, pi)
    hist: dict[str, float] = collections.defaultdict(float)
    for p in paths:
        for (a, b) in p.segments:
            L = math.dist(a, b)
            if L <= 0:
                continue
            ang = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
            hist[f"{int(ang / math.pi * 12) * 15:03d}"] += L
    s = sum(hist.values()) or 1.0
    c.angle_histogram = {k: v / s for k, v in sorted(hist.items())}

    xs = [p.bbox[0] for p in paths] + [p.bbox[2] for p in paths]
    ys = [p.bbox[1] for p in paths] + [p.bbox[3] for p in paths]
    if xs:
        c.bbox = (min(xs), min(ys), max(xs), max(ys))
        area = (c.bbox[2] - c.bbox[0]) * (c.bbox[3] - c.bbox[1])
        page_area = sheet.transform.width * sheet.transform.height or 1.0
        c.spatial_spread = area / page_area

    c.connectivity = _connectivity(paths, sheet.epsilon())


def _connectivity(paths: list[PathRecord], eps: float) -> float:
    """Andel banor med en andpunkt inom eps fran en annan bana i klustret."""
    if len(paths) < 2 or eps <= 0:
        return 0.0
    cell = max(eps * 2, 1e-6)
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    ends: list[tuple[int, tuple[float, float]]] = []
    for p in paths:
        if not p.segments:
            continue
        for pt in (p.segments[0][0], p.segments[-1][1]):
            ends.append((p.id, pt))
            grid[(int(pt[0] // cell), int(pt[1] // cell))].append(len(ends) - 1)
    hit: set[int] = set()
    for idx, (pid, pt) in enumerate(ends):
        gx, gy = int(pt[0] // cell), int(pt[1] // cell)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for other in grid.get((gx + i, gy + j), ()):
                    opid, opt = ends[other]
                    if opid != pid and math.dist(pt, opt) <= eps:
                        hit.add(pid)
                        break
    return len(hit) / len(paths)


def angular_concentration(c: StyleCluster) -> float:
    """Hur enriktat vinkelhistogrammet ar. 1.0 = allt i ett fack."""
    if not c.angle_histogram:
        return 0.0
    return max(c.angle_histogram.values())


def orthogonal_share(c: StyleCluster) -> float:
    """Andel langd som ligger i 0- eller 90-graders facken."""
    h = c.angle_histogram
    return h.get("000", 0.0) + h.get("090", 0.0)
