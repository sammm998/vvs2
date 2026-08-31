"""Noder, strak och vertikala ror.

Noder skapas EFTER sammanfogningen och endast dar natet verkligen andrar
karaktar: T- eller X-korsning och andpunkt utan fortsattning. Aldrig vid en
streckskarv - det var felet som gav en nod vid varje skarv i tidigare
versioner. En bojning raknas som handelse langs straket, inte som nod, sa att
ett strak far folja roret genom sina krokar.

Langd mats pa grafens kanter, aldrig pa banor. En kant raknas exakt en gang.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field

from .chain import Run, _polyline_length

Point = tuple[float, float]

# Riktningsandring som skapar en nod. En bojning ar en handelse i natet, inte
# ett langdmatt - graden ar en vinkel, inte ett matt i pt eller mm (R1).
NODE_ANGLE = math.radians(15.0)


@dataclass
class Strand:
    """Ett strak: sammanhangande kedja mellan tva noder. Enheten som mangdas."""

    id: int
    cluster_id: str
    points: list[Point]
    node_a: int
    node_b: int

    @property
    def length(self) -> float:
        return _polyline_length(self.points)


@dataclass
class Vertical:
    id: int
    center: Point
    size: float
    signature: tuple
    strand_id: int | None
    cluster_id: str


@dataclass
class Network:
    strands: list[Strand]
    nodes: list[Point]
    verticals: list[Vertical]
    bends: int = 0
    tees: int = 0

    @property
    def total_length(self) -> float:
        return sum(s.length for s in self.strands)

    def as_dict(self) -> dict:
        return {
            "strands": len(self.strands),
            "nodes": len(self.nodes),
            "verticals": len(self.verticals),
            "bends": self.bends,
            "tees": self.tees,
            "total_length_pt": round(self.total_length, 1),
        }


def _node_key(p: Point, eps: float) -> tuple[int, int]:
    return (int(round(p[0] / eps)), int(round(p[1] / eps)))


def build(runs_by_cluster: dict[str, list[Run]], eps: float) -> Network:
    """Bygg natet ur de sammanfogade polylinjerna."""
    nodes: list[Point] = []
    node_of: dict[tuple[int, int], int] = {}

    def node_id(p: Point) -> int:
        k = _node_key(p, eps)
        if k not in node_of:
            node_of[k] = len(nodes)
            nodes.append(p)
        return node_of[k]

    # Andpunkter och korsningar ar nodkandidater. En punkt dar tre eller fler
    # polylinjeandar mots ar en T- eller X-korsning.
    endpoint_count: collections.Counter = collections.Counter()
    for runs in runs_by_cluster.values():
        for r in runs:
            if len(r) < 2:
                continue
            endpoint_count[_node_key(r[0], eps)] += 1
            endpoint_count[_node_key(r[-1], eps)] += 1

    junction = {k for k, n in endpoint_count.items() if n >= 3}

    strands: list[Strand] = []
    bends = 0
    for cid, runs in runs_by_cluster.items():
        for r in runs:
            if len(r) < 2 or _polyline_length(r) <= 0:
                continue
            # En bojning ar en handelse LANGS ett strak, inte en nod. Straket
            # bryts bara vid verklig T- eller X-korsning och vid fri ande.
            # Att bryta vid varje bojning - eller varje streckskarv - var
            # felet bakom magenta punkter overallt i tidigare versioner.
            bends += _count_bends(r)
            for piece in _split_at_junctions(r, junction, eps):
                a, b = node_id(piece[0]), node_id(piece[-1])
                strands.append(Strand(len(strands), cid, piece, a, b))
    tees = len(junction)
    return Network(strands=strands, nodes=nodes, verticals=[], bends=bends, tees=tees)


def _count_bends(r: Run) -> int:
    n = 0
    for i in range(1, len(r) - 1):
        a0 = math.atan2(r[i][1] - r[i - 1][1], r[i][0] - r[i - 1][0])
        a1 = math.atan2(r[i + 1][1] - r[i][1], r[i + 1][0] - r[i][0])
        if abs(math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))) > NODE_ANGLE:
            n += 1
    return n


def _split_at_junctions(r: Run, junction: set, eps: float) -> list[Run]:
    out: list[Run] = []
    cur: Run = [r[0]]
    for i in range(1, len(r)):
        cur.append(r[i])
        if i < len(r) - 1 and _node_key(r[i], eps) in junction:
            out.append(cur)
            cur = [r[i]]
    if len(cur) >= 2:
        out.append(cur)
    return out or [r]


# --------------------------------------------------------------------------
# Vertikala ror


def _point_seg_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def symbol_instances(paths, expand: float) -> list[dict]:
    """Gruppera sma banor som overlappar till symbolinstanser."""
    n = len(paths)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    cell = max(expand * 8, 1e-6)
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for i, p in enumerate(paths):
        gx, gy = int(p.bbox[0] // cell), int(p.bbox[1] // cell)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                grid[(gx + di, gy + dj)].append(i)
    for i, p in enumerate(paths):
        gx, gy = int(p.bbox[0] // cell), int(p.bbox[1] // cell)
        for j in grid.get((gx, gy), ()):
            if j <= i:
                continue
            a, b = p.bbox, paths[j].bbox
            if not (a[2] + expand < b[0] or b[2] + expand < a[0] or a[3] + expand < b[1] or b[3] + expand < a[1]):
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb

    groups: dict[int, list] = collections.defaultdict(list)
    for i, p in enumerate(paths):
        groups[find(i)].append(p)

    out = []
    for g in groups.values():
        x0 = min(p.bbox[0] for p in g)
        y0 = min(p.bbox[1] for p in g)
        x1 = max(p.bbox[2] for p in g)
        y1 = max(p.bbox[3] for p in g)
        out.append(
            {
                "center": ((x0 + x1) / 2, (y0 + y1) / 2),
                "w": x1 - x0,
                "h": y1 - y0,
                "layer": g[0].layer,
                "signature": (round(x1 - x0, 1), round(y1 - y0, 1), sum(len(p.segments) for p in g)),
            }
        )
    return out


def find_verticals(
    net: Network,
    candidate_paths,
    cluster_of_layer: dict[str, str],
    unit: float,
    square_tol: float = 0.25,
) -> list[Vertical]:
    """Hitta stigar-/fallsymboler och kn~yt var och en till NARMASTE strak.

    Varje symbol ger exakt EN rakning, aldrig en per passerande strak. Det var
    felet bakom 149 vertikaler mot facit 55.

    En symbol maste vara ungefar kvadratisk (rotationssymmetrisk) och ligga PA
    ett strak - inom ``unit`` x 2, dar unit ar rorstilens medianlinjebredd.
    """
    instances = symbol_instances(candidate_paths, expand=unit * 0.7)
    on_run = unit * 2.0
    out: list[Vertical] = []
    for inst in instances:
        w, h = inst["w"], inst["h"]
        if max(w, h) <= 0 or abs(w - h) > square_tol * max(w, h):
            continue
        best_d, best_s = float("inf"), None
        for s in net.strands:
            for i in range(len(s.points) - 1):
                d = _point_seg_distance(inst["center"], s.points[i], s.points[i + 1])
                if d < best_d:
                    best_d, best_s = d, s
        if best_d > on_run:
            continue
        out.append(
            Vertical(
                id=len(out),
                center=inst["center"],
                size=max(w, h),
                signature=inst["signature"],
                strand_id=best_s.id if best_s else None,
                cluster_id=best_s.cluster_id if best_s else cluster_of_layer.get(inst["layer"], ""),
            )
        )
    net.verticals = out
    return out
