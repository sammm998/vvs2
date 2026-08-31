"""Fas 5 - text ur ritningen.

Riktiga PDF-textobjekt anvands forst. Ligger farre an 50 av dem i planytan ar
ritningstexten vektoriserad (SHX) och maste byggas upp ur glyfstreck:

    streck -> glyf -> ord -> rad

Alla matt harleds ur textens egen versalhojd, aldrig ur en pt-konstant (R1).

Darefter *induceras alfabetet*: varje glyf far en normaliserad formsignatur
och glyfer med samma form klustras ihop. Det ger, helt utan OCR, svaret pa
den fraga mangdningen faktiskt staller - vilka beteckningar som ar samma
beteckning. Vilket tecken varje formkluster motsvarar ar ett separat, mycket
mindre problem: ett fatal bilder i stallet for hundratals etiketter.
"""

from __future__ import annotations

import collections
import math
import statistics
from dataclasses import dataclass, field

from .extract import PathRecord, Sheet

Point = tuple[float, float]
Box = tuple[float, float, float, float]

GRID_W, GRID_H = 8, 12


@dataclass
class Glyph:
    id: int
    bbox: Box
    path_ids: list[int]
    shape: tuple
    cluster: int = -1

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]


@dataclass
class Word:
    id: int
    bbox: Box
    glyphs: list[Glyph]

    def code(self) -> tuple[int, ...]:
        """Ordets formkod. Lika kod = samma text, aven olast."""
        return tuple(g.cluster for g in self.glyphs)


@dataclass
class TextLine:
    id: int
    bbox: Box
    words: list[Word]
    cap_height: float
    source: str = "glyphs"   # "glyphs" | "pdf_text"
    text: str | None = None

    def code(self) -> tuple:
        return tuple(w.code() for w in self.words)

    @property
    def center(self) -> Point:
        return ((self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2)


@dataclass
class TextIndex:
    lines: list[TextLine]
    cap_height: float
    alphabet: dict[int, list[int]] = field(default_factory=dict)
    source: str = "glyphs"

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "lines": len(self.lines),
            "words": sum(len(l.words) for l in self.lines),
            "cap_height_pt": round(self.cap_height, 2),
            "alphabet_size": len(self.alphabet),
        }


# --------------------------------------------------------------------------


def cap_height(paths: list[PathRecord]) -> float:
    """Textens versalhojd, som typvardet bland de hogsta glyfstrecken.

    Referensmatt for alla avstand i modulen. Harleds ur ritningen (R1).
    """
    heights = [round(p.bbox[3] - p.bbox[1], 1) for p in paths if p.length > 0]
    heights = [h for h in heights if h > 0]
    if not heights:
        return 0.0
    top = sorted(heights)[int(len(heights) * 0.75) :]
    if not top:
        return max(heights)
    return collections.Counter(top).most_common(1)[0][0]


def _cluster_boxes(items, gap_x: float, gap_y: float) -> list[list]:
    """Gruppera lador som ligger inom (gap_x, gap_y) fran varandra."""
    n = len(items)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    cell = max(gap_x, gap_y, 1e-6) * 2
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for i, b in enumerate(items):
        grid[(int(b[0] // cell), int(b[1] // cell))].append(i)
    for i, a in enumerate(items):
        gx, gy = int(a[0] // cell), int(a[1] // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j <= i:
                        continue
                    b = items[j]
                    if a[0] - gap_x <= b[2] and b[0] - gap_x <= a[2] and \
                       a[1] - gap_y <= b[3] and b[1] - gap_y <= a[3]:
                        ra, rb = find(i), find(j)
                        if ra != rb:
                            parent[ra] = rb
    groups: dict[int, list[int]] = collections.defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values())


def _rasterise(paths: list[PathRecord], box: Box) -> tuple:
    """Normaliserad formsignatur: glyfen ritad i ett litet rutnat."""
    x0, y0, x1, y1 = box
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    bits = [0] * (GRID_W * GRID_H)
    step = max(w, h) / max(GRID_W, GRID_H)
    for p in paths:
        for a, b in p.segments:
            L = math.dist(a, b)
            # Steget foljer glyfens STORSTA sida. Att dela med den minsta
            # later ett plattt streck (h ~ 0) spranga antalet sampel.
            n = max(1, min(64, int(L / step) + 1))
            for k in range(n + 1):
                t = k / n
                px = a[0] + (b[0] - a[0]) * t
                py = a[1] + (b[1] - a[1]) * t
                gx = min(GRID_W - 1, max(0, int((px - x0) / w * GRID_W)))
                gy = min(GRID_H - 1, max(0, int((py - y0) / h * GRID_H)))
                bits[gy * GRID_W + gx] = 1
    # Bredd/hojd-forhallandet skiljer '-' fran '_' och '1' fran '.'
    aspect = round(min(4.0, w / h), 1) if h > 0 else 0.0
    return (aspect, tuple(bits))


def build(
    sheet: Sheet,
    candidate_paths: list[PathRecord],
    plan: Box | None = None,
    induce: bool = False,
) -> TextIndex:
    """Bygg rader ur glyfstreck, eller ur riktig PDF-text nar den racker.

    ``induce`` styr om alfabetet ska induceras. Ankarrostningen behover bara
    veta VAR etiketterna star, inte vad de star - formsignaturerna behovs
    forst nar mangden ska delas per beteckning.
    """
    real = [t for t in sheet.texts if plan is None or _inside(t.bbox, plan)]
    if len(real) >= 50:
        lines = [
            TextLine(
                id=i,
                bbox=t.bbox,
                words=[],
                cap_height=t.bbox[3] - t.bbox[1],
                source="pdf_text",
                text=t.text,
            )
            for i, t in enumerate(real)
        ]
        ch = statistics.median([l.cap_height for l in lines]) if lines else 0.0
        return TextIndex(lines=lines, cap_height=ch, source="pdf_text")

    paths = [p for p in candidate_paths if p.length > 0]
    if not paths:
        return TextIndex(lines=[], cap_height=0.0, source="glyphs")
    ch = cap_height(paths)
    if ch <= 0:
        return TextIndex(lines=[], cap_height=0.0, source="glyphs")

    # streck -> glyf: streck inom en brakdel av versalhojden hor ihop
    boxes = [p.bbox for p in paths]
    glyph_groups = _cluster_boxes(boxes, gap_x=ch * 0.10, gap_y=ch * 0.10)
    glyphs: list[Glyph] = []
    for gi, idxs in enumerate(glyph_groups):
        gp = [paths[i] for i in idxs]
        bb = (
            min(p.bbox[0] for p in gp),
            min(p.bbox[1] for p in gp),
            max(p.bbox[2] for p in gp),
            max(p.bbox[3] for p in gp),
        )
        if bb[2] - bb[0] > ch * 3 or bb[3] - bb[1] > ch * 2.5:
            continue  # for stort for att vara ett tecken
        shape = _rasterise(gp, bb) if induce else ()
        glyphs.append(Glyph(gi, bb, [p.id for p in gp], shape))

    # glyf -> ord: mellanrum inom ordet ar mindre an ~0,4 versalhojder
    gboxes = [g.bbox for g in glyphs]
    word_groups = _cluster_boxes(gboxes, gap_x=ch * 0.40, gap_y=ch * 0.15)
    words: list[Word] = []
    for wi, idxs in enumerate(word_groups):
        gs = sorted((glyphs[i] for i in idxs), key=lambda g: g.bbox[0])
        bb = (
            min(g.bbox[0] for g in gs),
            min(g.bbox[1] for g in gs),
            max(g.bbox[2] for g in gs),
            max(g.bbox[3] for g in gs),
        )
        words.append(Word(wi, bb, gs))

    # ord -> rad: samma baslinje, glesare mellanrum
    wboxes = [w.bbox for w in words]
    line_groups = _cluster_boxes(wboxes, gap_x=ch * 1.2, gap_y=ch * 0.25)
    lines: list[TextLine] = []
    for li, idxs in enumerate(line_groups):
        ws = sorted((words[i] for i in idxs), key=lambda w: w.bbox[0])
        bb = (
            min(w.bbox[0] for w in ws),
            min(w.bbox[1] for w in ws),
            max(w.bbox[2] for w in ws),
            max(w.bbox[3] for w in ws),
        )
        lines.append(TextLine(li, bb, ws, ch))

    alphabet = induce_alphabet(glyphs) if induce else {}
    return TextIndex(lines=lines, cap_height=ch, alphabet=alphabet, source="glyphs")


def induce_alphabet(glyphs: list[Glyph], tol: float = 0.10) -> dict[int, list[int]]:
    """Klustra glyfer pa form. Samma form = samma tecken, aven olast.

    Exakt matchning forst - samma typsnitt renderar tecknet likadant varje
    gang - och darefter sammanslagning av kluster som skiljer sig pa hogst
    ``tol`` av rutnatets celler.
    """
    exact: dict[tuple, list[int]] = collections.defaultdict(list)
    for g in glyphs:
        exact[g.shape].append(g.id)

    keys = sorted(exact, key=lambda k: -len(exact[k]))
    reps: list[tuple] = []
    assign: dict[tuple, int] = {}
    budget = int(GRID_W * GRID_H * tol)
    for k in keys:
        placed = False
        for ci, rep in enumerate(reps):
            if abs(k[0] - rep[0]) > 0.35:
                continue
            if sum(a != b for a, b in zip(k[1], rep[1])) <= budget:
                assign[k] = ci
                placed = True
                break
        if not placed:
            assign[k] = len(reps)
            reps.append(k)

    by_id = {g.id: g for g in glyphs}
    out: dict[int, list[int]] = collections.defaultdict(list)
    for k, ids in exact.items():
        ci = assign[k]
        for gid in ids:
            by_id[gid].cluster = ci
            out[ci].append(gid)
    return dict(out)


def _inside(box: Box, outer: Box) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]
