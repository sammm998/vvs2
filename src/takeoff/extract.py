"""Extraktion av banor och text ur en vektor-PDF.

All geometri passerar normalize.PageTransform (R8). Ingenting filtreras bort
har: varje bana i ritningen far en post. Vad som senare accepteras eller
sparras avgors i pipeline-stegen, och tackningen (R6) mats mot ``len(paths)``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

import pymupdf

from .normalize import PageTransform, Point, page_transform

Segment = tuple[Point, Point]


@dataclass
class PathRecord:
    """En ritad bana, normaliserad."""

    id: int
    seqno: int
    layer: str | None
    kind: str  # 's' | 'f' | 'fs'
    stroke: tuple[float, float, float] | None
    fill: tuple[float, float, float] | None
    width: float
    dashes: str
    dash_signature: str
    line_cap: int
    closed: bool
    bbox: tuple[float, float, float, float]
    segments: list[Segment] = field(default_factory=list)

    @property
    def length(self) -> float:
        return sum(math.dist(a, b) for a, b in self.segments)

    @property
    def n_segments(self) -> int:
        return len(self.segments)

    def angles(self) -> list[float]:
        """Segmentriktningar i radianer, vikta mod pi (riktningslosa)."""
        out = []
        for a, b in self.segments:
            if math.dist(a, b) <= 0:
                continue
            out.append(math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi)
        return out


@dataclass
class TextRecord:
    id: int
    text: str
    bbox: tuple[float, float, float, float]
    block: int
    line: int
    word: int

    @property
    def center(self) -> Point:
        x0, y0, x1, y1 = self.bbox
        return ((x0 + x1) / 2, (y0 + y1) / 2)


@dataclass
class Sheet:
    """Allt som lastes ur en sida."""

    source: str
    page_number: int
    transform: PageTransform
    paths: list[PathRecord]
    texts: list[TextRecord]
    ocgs: dict[int, dict]

    @property
    def has_ocgs(self) -> bool:
        return any(p.layer for p in self.paths)

    @property
    def layers(self) -> list[str]:
        return sorted({p.layer for p in self.paths if p.layer})

    def median_width(self) -> float:
        w = [p.width for p in self.paths if p.width > 0]
        return statistics.median(w) if w else 0.0

    def median_segment_length(self) -> float:
        lens = [math.dist(a, b) for p in self.paths for a, b in p.segments if math.dist(a, b) > 0]
        return statistics.median(lens) if lens else 0.0

    def epsilon(self) -> float:
        """Grundepsilon for narhetsfragor. Relativ, aldrig absolut (R1)."""
        mw = self.median_width()
        return mw if mw > 0 else self.transform.diagonal * 1e-4


def dash_signature(dashes: str | None) -> str:
    """Normaliserad strecksignatur - oberoende av absolut streckskala (R1)."""
    if not dashes:
        return "solid"
    s = dashes.strip()
    if s in ("[] 0", "[]0", "[] 0.0"):
        return "solid"
    try:
        inner = s[s.index("[") + 1 : s.index("]")]
        terms = [float(t) for t in inner.split()]
    except (ValueError, IndexError):
        return f"raw:{s}"
    if not terms or all(t == 0 for t in terms):
        return "solid"
    period = sum(terms)
    return "n%d:%s" % (len(terms), "/".join(f"{t / period:.2f}" for t in terms))


def _flatten(items, tf: PageTransform) -> tuple[list[Segment], bool]:
    """Platta ut ett pymupdf-item till segment i normrymden."""
    segs: list[Segment] = []
    closed = False
    for it in items:
        op = it[0]
        if op == "l":
            segs.append((tf.apply(it[1]), tf.apply(it[2])))
        elif op == "c":
            # Bezier -> polygon. Antal delar skalas med kontrollpolygonens
            # langd, inte med en fast konstant.
            p = [tf.apply(it[i]) for i in (1, 2, 3, 4)]
            ctrl = sum(math.dist(p[i], p[i + 1]) for i in range(3))
            n = max(2, min(24, int(ctrl / max(tf.diagonal * 5e-4, 1e-6))))
            prev = p[0]
            for k in range(1, n + 1):
                t = k / n
                mt = 1 - t
                x = (
                    mt**3 * p[0][0]
                    + 3 * mt**2 * t * p[1][0]
                    + 3 * mt * t**2 * p[2][0]
                    + t**3 * p[3][0]
                )
                y = (
                    mt**3 * p[0][1]
                    + 3 * mt**2 * t * p[1][1]
                    + 3 * mt * t**2 * p[2][1]
                    + t**3 * p[3][1]
                )
                segs.append((prev, (x, y)))
                prev = (x, y)
        elif op == "re":
            r = tf.apply_rect(it[1])
            c = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
            segs.extend((c[i], c[(i + 1) % 4]) for i in range(4))
            closed = True
        elif op == "qu":
            q = it[1]
            c = [tf.apply(p) for p in (q.ul, q.ur, q.lr, q.ll)]
            segs.extend((c[i], c[(i + 1) % 4]) for i in range(4))
            closed = True
    return segs, closed


def load(source: str, page_number: int = 0) -> Sheet:
    doc = pymupdf.open(source)
    page = doc[page_number]
    tf = page_transform(page)
    paths: list[PathRecord] = []
    for i, d in enumerate(page.get_drawings()):
        segs, closed_shape = _flatten(d["items"], tf)
        cap = d.get("lineCap")
        if isinstance(cap, (tuple, list)):
            cap = cap[0] if cap else 0
        paths.append(
            PathRecord(
                id=i,
                seqno=int(d.get("seqno", i)),
                layer=d.get("layer"),
                kind=d.get("type", "s"),
                stroke=tuple(d["color"]) if d.get("color") else None,
                fill=tuple(d["fill"]) if d.get("fill") else None,
                width=float(d.get("width") or 0.0) * tf.scale_factor,
                dashes=d.get("dashes") or "",
                dash_signature=dash_signature(d.get("dashes")),
                line_cap=int(cap or 0),
                closed=bool(d.get("closePath")) or closed_shape,
                bbox=tuple(tf.apply_rect(d["rect"])),
                segments=segs,
            )
        )
    texts = [
        TextRecord(
            id=j,
            text=w[4],
            bbox=tuple(tf.apply_rect(w[:4])),
            block=int(w[5]),
            line=int(w[6]),
            word=int(w[7]),
        )
        for j, w in enumerate(page.get_text("words"))
    ]
    sheet = Sheet(
        source=source,
        page_number=page_number,
        transform=tf,
        paths=paths,
        texts=texts,
        ocgs=doc.get_ocgs(),
    )
    doc.close()
    return sheet


def corner_split(path: PathRecord, factor: float = 3.0) -> list[list[Segment]]:
    """Dela en bana i delkedjor vid riktningsandringar over ``factor`` x
    medianvinkelandringen i banan.

    Relativ troskel enligt R1: ingen grad- eller punktkonstant.
    """
    segs = [s for s in path.segments if math.dist(*s) > 0]
    if len(segs) < 2:
        return [segs] if segs else []
    turns = []
    for i in range(len(segs) - 1):
        a0 = math.atan2(segs[i][1][1] - segs[i][0][1], segs[i][1][0] - segs[i][0][0])
        a1 = math.atan2(segs[i + 1][1][1] - segs[i + 1][0][1], segs[i + 1][1][0] - segs[i + 1][0][0])
        turns.append(abs(math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))))
    med = statistics.median(turns)
    thr = max(med * factor, 1e-9)
    out: list[list[Segment]] = [[segs[0]]]
    for i, t in enumerate(turns):
        if t > thr:
            out.append([segs[i + 1]])
        else:
            out[-1].append(segs[i + 1])
    return out
