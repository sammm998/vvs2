"""R7 - klusterklassificering och val av rorstil.

Ordningen ar stil fore geometri. Vi klassificerar aldrig en enskild bana; vi
klassificerar stilklustret och later hela klustret folja med.

Rorstilen valjs i tva steg:

1. Negativa filter pa *klusternivá* stryker ram, text, schraffering, vagg och
   hanvisningsstreck. Varje struken bana skrivs till blocked_paths med orsak
   och steg (R6).
2. De kluster som ater kvar rangordnas pa strukturella egenskaper som
   uttrycks som percentiler av ritningens egen fordelning (R1): linjebredd
   over ritningens median, hog kopplingsgrad, langa banor, stor rumslig
   spridning, och laget innanfor planytan.

Nar beteckningsankare finns (fas 5-6) roster de fram klustret i stallet, och
den strukturella rangordningen blir bara en kontroll. Sa lange ankare saknas
markeras resultatet med flaggan ``pipe_style:structural`` sa att det aldrig
kan misstas for ankarbelagd matning (R3).
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field

from .extract import Sheet
from .styles import StyleCluster, StyleIndex, angular_concentration

# Andel banor i ett kluster som maste mota en annan bana i samma kluster for
# att klustret ska kunna vara ett ledningsnat. Dimensionslos andel, inget matt.
MIN_CONNECTIVITY = 0.10


@dataclass
class Blocked:
    path_id: int
    cluster_id: str
    reason: str
    step: str


@dataclass
class PipeSelection:
    pipe_clusters: list[str]
    blocked: list[Blocked]
    scores: dict[str, float]
    reasons: dict[str, str]
    method: str
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "method": self.method,
            "pipe_clusters": self.pipe_clusters,
            "flags": self.flags,
            "classification": self.reasons,
            "scores": {k: round(v, 3) for k, v in self.scores.items()},
        }


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[max(0, min(len(v) - 1, int(len(v) * p)))]


def classify(
    sheet: Sheet,
    styles: StyleIndex,
    zonemap,
    scale_result,
    anchors: dict[str, int] | None = None,
) -> PipeSelection:
    """Klassificera alla stilkluster och valj rorstilen."""
    blocked: list[Blocked] = []
    reasons: dict[str, str] = {}
    scores: dict[str, float] = {}
    flags: list[str] = []
    by_id = {p.id: p for p in sheet.paths}

    widths = [p.width for p in sheet.paths if p.width > 0]
    w_med = _pct(widths, 0.5)
    lengths = [c.length_p50 for c in styles.clusters if c.length_p50 > 0]
    len_med = _pct(lengths, 0.5)

    # ---- steg 1: negativa filter, klusternivá -------------------------------
    for c in styles.clusters:
        why = _negative(c, sheet, styles, zonemap, scale_result, by_id, w_med, len_med)
        if why:
            reasons[c.id] = why
            for pid in c.path_ids:
                blocked.append(Blocked(pid, c.id, why, "negative_filter"))

    survivors = [c for c in styles.clusters if c.id not in reasons]

    # ---- steg 1b: strukturella grindar --------------------------------------
    # Installationen ritas grovre an underlaget. Grinden ar ritningens egen
    # medianlinjebredd, inte ett matt i punkter (R1).
    # Ror bildar dessutom nat: ett rorkluster har banor som mots i andpunkter.
    # Ett kluster av losa symboler eller markeringar har det inte.
    gated = []
    for c in survivors:
        if c.width <= w_med * 1.02:
            reasons[c.id] = "thin_for_service_layer"
        elif c.connectivity <= MIN_CONNECTIVITY:
            reasons[c.id] = "unconnected"
        else:
            gated.append(c)
            continue
        for pid in c.path_ids:
            blocked.append(Blocked(pid, c.id, reasons[c.id], "structural_gate"))
    survivors = gated

    # ---- steg 2: rorstilsval ------------------------------------------------
    if anchors:
        total_votes = sum(anchors.values()) or 1
        ranked = sorted(anchors, key=lambda k: -anchors[k])
        cumulative, chosen = 0, []
        for cid in ranked:
            cumulative += anchors[cid]
            chosen.append(cid)
            if cumulative / total_votes > 0.70:
                break
        method = "anchor_vote"
        pipe_ids = [c.id for c in survivors if c.id in chosen]
    else:
        # Utan ankare ar grindarna ovan sjalva urvalet. Poangen redovisas som
        # rangordning och osakerhetsmatt, inte som ytterligare ett filter -
        # ett andra troskelsteg har ingen ritningsburen grund.
        method = "structural"
        flags.append("pipe_style:structural")
        for c in survivors:
            scores[c.id] = _structural_score(c, sheet, zonemap, w_med)
        pipe_ids = [c.id for c in survivors]

    for c in survivors:
        if c.id not in pipe_ids:
            reasons[c.id] = reasons.get(c.id, "not_pipe_style")
            for pid in c.path_ids:
                blocked.append(Blocked(pid, c.id, "not_pipe_style", "style_vote"))
        else:
            reasons[c.id] = "pipe"

    accepted = sum(len(styles.get(cid).path_ids) for cid in pipe_ids)
    assert accepted + len(blocked) == len(sheet.paths), (
        f"R6: {accepted} accepterade + {len(blocked)} sparrade != {len(sheet.paths)} totalt"
    )
    return PipeSelection(sorted(pipe_ids), blocked, scores, reasons, method, flags)


def _negative(
    c: StyleCluster,
    sheet: Sheet,
    styles: StyleIndex,
    zonemap,
    scale_result,
    by_id,
    w_med: float,
    len_med: float,
) -> str | None:
    if c.total_length <= 0:
        return "degenerate"

    # Ram: klustrets tyngdpunkt ligger utanfor planytan.
    if _outside_plan_share(c, by_id, zonemap) > 0.5:
        return "frame"

    # Text och glyfer: manga korta banor, liten yta per bana, lag koppling.
    if c.n_paths >= 30 and c.length_p90 < len_med and c.connectivity < 0.25:
        return "text_or_glyph"

    # Schraffering: enriktat vinkelhistogram plus hog lokal tathet.
    if angular_concentration(c) > 0.8 and c.n_paths >= 30 and c.length_p50 < len_med:
        return "hatch"

    # Vagg: hog kollinearitet i parallella par pa vaggavstand.
    if scale_result and scale_result.value:
        if _wall_pair_share(c, by_id, sheet, scale_result) > 0.5:
            return "wall"
    return None


def _outside_plan_share(c: StyleCluster, by_id, zonemap) -> float:
    if zonemap is None:
        return 0.0
    total = 0.0
    outside = 0.0
    for pid in c.path_ids:
        p = by_id[pid]
        L = max(p.length, 1e-9)
        total += L
        if zonemap.classify(p.bbox) != "plan":
            outside += L
    return outside / total if total else 0.0


def _wall_pair_share(c: StyleCluster, by_id, sheet: Sheet, scale_result) -> float:
    """Andel langd i kollinjara parallella par pa 60-500 mm avstand."""
    from .scale import WALL_MM_MAX, WALL_MM_MIN

    lo = scale_result.mm_to_pt(WALL_MM_MIN)
    hi = scale_result.mm_to_pt(WALL_MM_MAX)
    segs = []
    for pid in c.path_ids:
        for a, b in by_id[pid].segments:
            L = math.dist(a, b)
            if L > hi:
                segs.append((a, b, L, math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi))
    if len(segs) < 8:
        return 0.0
    total = sum(s[2] for s in segs)
    paired = 0.0
    for target in (0.0, math.pi / 2):
        sel = [s for s in segs if min(abs(s[3] - target), math.pi - abs(s[3] - target)) < 0.02]
        axis = 1 if target == 0.0 else 0
        other = 1 - axis
        sel.sort(key=lambda s: s[0][axis])
        for i, s in enumerate(sel):
            for t in sel[i + 1 :]:
                d = abs(t[0][axis] - s[0][axis])
                if d > hi:
                    break
                if d < lo:
                    continue
                ov_lo = max(min(s[0][other], s[1][other]), min(t[0][other], t[1][other]))
                ov_hi = min(max(s[0][other], s[1][other]), max(t[0][other], t[1][other]))
                if ov_hi - ov_lo > 0.7 * min(s[2], t[2]):
                    paired += s[2]
                    break
    return paired / total if total else 0.0


def _structural_score(c: StyleCluster, sheet: Sheet, zonemap, w_med: float) -> float:
    """Strukturpoang i [0, 1]. Alla termer relativa till ritningen sjalv."""
    # Rorlinjer ritas grovre an underlaget.
    heavy = 1.0 if c.width > w_med else 0.0
    # Ror bildar nat: andparter mots.
    conn = min(1.0, c.connectivity)
    # Ror lopar langt jamfort med ritningens ovriga banor.
    reach = min(1.0, c.length_p90 / max(sheet.transform.diagonal * 0.01, 1e-9))
    # Ror ligger utspridda over planet, inte i en ruta.
    spread = min(1.0, c.spatial_spread / 0.2)
    return 0.40 * heavy + 0.25 * conn + 0.20 * reach + 0.15 * spread
