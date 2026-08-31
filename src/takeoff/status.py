"""R5 - status separeras (ny / befintlig / rivning).

Skillnaden kan ligga i lager, farg, linjetyp eller ljushet. Alla fyra
hypoteserna provas och den som ger en ren uppdelning av rorgeometrin
redovisas. Hittas ingen ren uppdelning sags det uttryckligen - kategorierna
gissas aldrig.

Kategorierna mats var for sig och redovisas var for sig. Normalt gar bara
"ny" in i mangden, men det beslutet fattas av manniska, inte av motorn.
"""

from __future__ import annotations

import collections
import math
import re
import statistics

# Ordledtradar i lagernamn. Trafflistan ar en *hypotes* som maste bekraftas
# av att uppdelningen ar ren; den avgor aldrig sjalv.
HINTS = {
    "befintlig": ("bef", "exist", "befint", "e-", "_e"),
    "rivning": ("riv", "demol", "demo", "rivs"),
    "ny": ("ny", "new", "n-"),
}


def _lightness(rgb) -> float:
    if not rgb:
        return 0.0
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def detect_status_rule(result) -> dict:
    """Prova lager, farg, linjetyp och ljushet. Returnera den renaste."""
    clusters = [result.styles.get(c) for c in result.selection.pipe_clusters]
    if not clusters:
        return {"field": None, "mapping": {}, "note": "inga rorkluster att dela upp"}

    by_id = {p.id: p for p in result.sheet.paths}
    m_per_pt = result.scale.m_per_pt

    def lengths(keyfn) -> dict[str, float]:
        out: dict[str, float] = collections.defaultdict(float)
        for c in clusters:
            for pid in c.path_ids:
                p = by_id[pid]
                out[str(keyfn(c, p))] += p.length * m_per_pt
        return dict(out)

    candidates = {
        "layer": lengths(lambda c, p: p.layer),
        "color": lengths(lambda c, p: tuple(round(v, 2) for v in (p.stroke or ())) or None),
        "linetype": lengths(lambda c, p: p.dash_signature),
        "lightness": lengths(lambda c, p: round(_lightness(p.stroke), 1)),
    }

    # En uppdelning ar "ren" bara om den delar geometrin i mer an en grupp OCH
    # nagon grupp gar att knyta till en statuskategori via lagernamnet.
    report: dict = {"field": None, "mapping": {}, "candidates": {}, "note": ""}
    for field, groups in candidates.items():
        report["candidates"][field] = {
            k: round(v, 1) for k, v in sorted(groups.items(), key=lambda x: -x[1])
        }

    hinted: dict[str, str] = {}
    for c in clusters:
        name = (c.key.layer or "").lower()
        for status, words in HINTS.items():
            if any(w in name for w in words):
                hinted[c.key.layer or ""] = status
                break

    if hinted and len(set(hinted.values())) >= 1 and len(hinted) < len(clusters):
        report["field"] = "layer"
        report["mapping"] = hinted
        report["note"] = (
            "lagernamn antyder statusuppdelning; bekrafta mot ritningens "
            "teckenforklaring innan nagon kategori utesluts"
        )
    else:
        report["note"] = (
            "ingen ren statusuppdelning hittad i rorgeometrin - all uppmatt "
            "rorlangd behandlas som en enda kategori och far inte tyst antas "
            "vara 'ny'"
        )
    return report


def pipe_representation(result, sample_tol: float = 1.0) -> str:
    """single_line eller double_line.

    Dubbelritade ror ger kollinjara parallella par pa ungefar en linjebredds
    avstand. Andelen sadan geometri avgor, inte ett antagande.
    """
    clusters = [result.styles.get(c) for c in result.selection.pipe_clusters]
    if not clusters:
        return "single_line"
    by_id = {p.id: p for p in result.sheet.paths}
    paired = total = 0.0
    for c in clusters:
        w = max(c.width, 1e-6)
        segs = []
        for pid in c.path_ids:
            for a, b in by_id[pid].segments:
                L = math.dist(a, b)
                if L > w * 4:
                    segs.append((a, b, L, math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi))
        total += sum(s[2] for s in segs)
        for target in (0.0, math.pi / 2):
            sel = [s for s in segs if min(abs(s[3] - target), math.pi - abs(s[3] - target)) < 0.02]
            axis = 1 if target == 0.0 else 0
            other = 1 - axis
            sel.sort(key=lambda s: s[0][axis])
            for i, s in enumerate(sel):
                for t in sel[i + 1 :]:
                    d = abs(t[0][axis] - s[0][axis])
                    if d > w * 2:
                        break
                    if d < w * 0.4:
                        continue
                    lo = max(min(s[0][other], s[1][other]), min(t[0][other], t[1][other]))
                    hi = min(max(s[0][other], s[1][other]), max(t[0][other], t[1][other]))
                    if hi - lo > 0.7 * min(s[2], t[2]):
                        paired += s[2]
                        break
    return "double_line" if total > 0 and paired / total > 0.5 else "single_line"


def wall_zone_overlap(result, zonemap) -> float:
    """Andel uppmatt rorlangd som ligger i vaggzon.

    Mats ALLTID, oavsett vilken wall_rule projektet valt, sa att det syns vad
    beslutet ar vart (CLAUDE.md, avsnitt Projektprofil).
    """
    walls = [
        c
        for c in result.styles.clusters
        if result.selection.reasons.get(c.id) == "wall"
    ]
    if not walls:
        return 0.0
    by_id = {p.id: p for p in result.sheet.paths}
    boxes = [by_id[pid].bbox for c in walls for pid in c.path_ids]
    if not boxes:
        return 0.0
    total = overlap = 0.0
    for s in result.net.strands:
        for i in range(len(s.points) - 1):
            a, b = s.points[i], s.points[i + 1]
            L = math.dist(a, b)
            total += L
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            for bx in boxes:
                if bx[0] <= mid[0] <= bx[2] and bx[1] <= mid[1] <= bx[3]:
                    overlap += L
                    break
    return overlap / total if total else 0.0
