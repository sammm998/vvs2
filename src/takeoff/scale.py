"""R4 - skalan verifieras geometriskt, aldrig antas.

Tre oberoende kallor:

``grid``      Modulnat: numeriska textetiketter i en rad eller kolumn med
              jamn delning. Etikettens *vardeskillnad* ar ett fysiskt matt i
              modulenheten, vilket gor natet sjalvkalibrerande.
``scalebar``  Skalstock i ramzonen: avlang fylld stapel med glyfgrupper i
              regelbunden delning ovanfor.
``wall``      Modal parallellavstand i ortogonala byggnadslager. Ger ingen
              exakt skala men en rimlighetsgrind: en byggnadsvagg ar 60-500 mm.

Minst tva kallor maste stamma inom 0,5 %. Vid storre avvikelse satts
``verified = False`` och orsaken skrivs som en strukturerad flagga. Systemet
antar aldrig en skala tyst.
"""

from __future__ import annotations

import collections
import math
import re
import statistics
from dataclasses import dataclass, field

from .extract import Sheet

PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0

# Standardskalor for byggritningar. Kandidater utanfor mangden forkastas.
STANDARD_SCALES = (10, 20, 25, 50, 100, 200, 250, 500, 1000)

# Fysiskt rimlig vaggtjocklek i mm. Anges i CLAUDE.md fas 4/6 och ar en
# uppgift om byggnader, inte en troskel kalibrerad mot en ritning.
WALL_MM_MIN, WALL_MM_MAX = 60.0, 500.0

# Enhetshypoteser. Modulnat etiketteras i cm, dm eller m; en skalstock spanner
# ett helt antal meter. Ingen av dem valjs tyst - alla provas och snittet mot
# ovriga kallor avgor.
GRID_LABEL_UNITS_MM = (10.0, 100.0, 1000.0)
SCALEBAR_SPAN_MM = (1000.0, 2000.0, 5000.0, 10000.0, 20000.0, 50000.0, 100000.0)


@dataclass
class ScaleSource:
    """En geometrisk kalla.

    En kalla mater en langd pa arket vars verkliga matt ar kant sa nar som pa
    vilken enhet som avses. Den levererar darfor en *mangd* kandidatskalor,
    en per enhetshypotes - aldrig ett tyst antagande om vilken som galler.
    Svaret ar snittet mellan kallornas mangder.
    """

    name: str
    pitch_pt: float
    candidates: dict[float, float]  # standardskala -> raa skala fore avrundning
    detail: dict = field(default_factory=dict)

    @property
    def scale(self) -> float:
        return min(self.candidates.values()) if self.candidates else 0.0

    @property
    def ok(self) -> bool:
        return bool(self.candidates)


def _candidate_scales(pitch_pt: float, unit_hypotheses: tuple[float, ...]) -> dict[float, float]:
    """Kandidatskalor for en uppmatt delning och en uppsattning enhetsgissningar."""
    out: dict[float, float] = {}
    for unit_mm in unit_hypotheses:
        raw = unit_mm * PT_PER_MM / pitch_pt
        snap = _snap(raw)
        if snap is not None:
            out[snap] = raw
    return out


@dataclass
class ScaleReference:
    """Skalstockens verkliga spann, faststallt pa en kalibrerad ritning.

    En skalstock ar en KAND GEOMETRISK LANGD sa snart man vet hur manga meter
    den spanner. Det gar inte att lasa ur en vektoriserad etikett, men det gar
    att faststalla pa en ritning dar modulnatet finns som riktig text - och
    darefter ateranvandas pa ovriga ritningar i SAMMA projekt (R2), sa lange
    stocken ar densamma.

    Referensen ar falsifierbar: skiljer sig stapelns langd eller delning fran
    den kalibrerade galler den inte, och skalan far inte faststallas ur den.
    """

    project_key: str
    pitch_pt: float
    divisions: int
    span_mm: float
    calibrated_on: str = ""

    def matches(self, source: "ScaleSource | None") -> bool:
        if source is None or source.name != "scalebar":
            return False
        if self.pitch_pt <= 0:
            return False
        if abs(source.pitch_pt - self.pitch_pt) / self.pitch_pt > 0.005:
            return False
        return int(source.detail.get("divisions") or 0) == self.divisions

    def as_dict(self) -> dict:
        return {
            "project_key": self.project_key,
            "pitch_pt": round(self.pitch_pt, 4),
            "divisions": self.divisions,
            "span_mm": self.span_mm,
            "calibrated_on": self.calibrated_on,
        }

    @staticmethod
    def from_dict(d: dict | None) -> "ScaleReference | None":
        if not d:
            return None
        return ScaleReference(
            project_key=d.get("project_key") or "",
            pitch_pt=float(d.get("pitch_pt") or 0.0),
            divisions=int(d.get("divisions") or 0),
            span_mm=float(d.get("span_mm") or 0.0),
            calibrated_on=d.get("calibrated_on") or "",
        )


def reference_from(result_scale: "ScaleResult", project_key: str, drawing: str) -> ScaleReference | None:
    """Harled projektreferensen ur en ritning med verifierad skala."""
    if not result_scale.verified or not result_scale.value:
        return None
    sb = next((s for s in result_scale.sources if s.name == "scalebar"), None)
    if sb is None:
        return None
    span_mm = sb.pitch_pt * MM_PER_PT * result_scale.value
    return ScaleReference(
        project_key=project_key,
        pitch_pt=sb.pitch_pt,
        divisions=int(sb.detail.get("divisions") or 0),
        span_mm=round(span_mm, 1),
        calibrated_on=drawing,
    )


@dataclass
class ScaleResult:
    value: float | None
    verified: bool
    sources: list[ScaleSource]
    error_pct: float | None
    flags: list[str] = field(default_factory=list)
    candidates: list[float] = field(default_factory=list)

    @property
    def m_per_pt(self) -> float:
        if not self.value:
            raise ValueError("skala ej faststalld - matning far inte ske")
        return MM_PER_PT * self.value / 1000.0

    def to_m(self, pt: float) -> float:
        return pt * self.m_per_pt

    def mm_to_pt(self, mm: float) -> float:
        """Fysiskt matt i verkligheten -> punkter pa arket."""
        if not self.value:
            raise ValueError("skala ej faststalld")
        return mm / self.value * PT_PER_MM

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "verified": self.verified,
            "sources": [s.name for s in self.sources],
            "error_pct": None if self.error_pct is None else round(self.error_pct, 4),
            "flags": self.flags,
            "candidates": self.candidates,
            "detail": {s.name: {"pitch_pt": round(s.pitch_pt, 4), "candidates": {int(k): round(v, 3) for k, v in s.candidates.items()}, **s.detail} for s in self.sources},
        }


# --------------------------------------------------------------------------
# Kalla 1: modulnat


_GRID_LABEL = re.compile(r"^([^\W\d_]*)[\s-]?(\d+(?:[.,]\d+)?)$", re.UNICODE)


def _numeric(t: str) -> tuple[str, float] | None:
    """Modulnatets etikett som (prefix, varde).

    Natbubblor heter inte alltid bara "70" - de heter lika ofta "A200" eller
    "B12". Prefixet bevaras sa att bara etiketter ur SAMMA natserie jamfors;
    att blanda A-serien med sifferserien vore att mata mellan tva olika nat.

    Etiketter med mer an en siffergrupp ("2024-04-19") ar inte natbubblor och
    forkastas.
    """
    s = t.strip()
    m = _GRID_LABEL.match(s)
    if not m:
        return None
    return (m.group(1).upper(), float(m.group(2).replace(",", ".")))


def grid_source(sheet: Sheet) -> ScaleSource | None:
    pts = []
    for t in sheet.texts:
        parsed = _numeric(t.text)
        if parsed is None:
            continue
        prefix, v = parsed
        x0, y0, x1, y1 = t.bbox
        pts.append((prefix, v, (x0 + x1) / 2, (y0 + y1) / 2, y1 - y0))
    if len(pts) < 3:
        return None
    heights = [p[4] for p in pts] or [1.0]
    tol = statistics.median(heights)

    best = None
    for axis in (0, 1):  # 0 = rad (gemensam y), 1 = kolumn (gemensam x)
        buckets: dict[tuple[str, int], list] = collections.defaultdict(list)
        for prefix, v, cx, cy, h in pts:
            along, across = (cx, cy) if axis == 0 else (cy, cx)
            buckets[(prefix, int(across / max(tol, 1e-6)))].append((v, along))
        for (prefix, _), group in buckets.items():
            if len(group) < 3:
                continue
            group.sort(key=lambda g: g[1])
            vals = [g[0] for g in group]
            pos = [g[1] for g in group]
            ratios = []
            for i in range(len(group) - 1):
                dv = vals[i + 1] - vals[i]
                dp = pos[i + 1] - pos[i]
                # Natet far numreras at bada hallen; det som kravs ar att
                # riktningen ar densamma hela raden.
                if dv == 0 or dp <= 0:
                    ratios = []
                    break
                ratios.append(dp / dv)
            if len(ratios) < 2 or not (all(r > 0 for r in ratios) or all(r < 0 for r in ratios)):
                continue
            ratios = [abs(r) for r in ratios]
            mean = statistics.fmean(ratios)
            spread = (max(ratios) - min(ratios)) / mean if mean else 1.0
            if best is None or spread < best[0]:
                best = (spread, mean, group)
    if best is None:
        return None
    spread, pitch, group = best
    if spread > 0.02:  # relativ; natet ar inte regelbundet nog
        return None
    return ScaleSource(
        "grid",
        pitch,
        _candidate_scales(pitch, GRID_LABEL_UNITS_MM),
        {"labels": [g[0] for g in group], "spread_pct": round(spread * 100, 3)},
    )


# --------------------------------------------------------------------------
# Kalla 2: skalstock


def scalebar_source(sheet: Sheet, plan) -> ScaleSource | None:
    """Hitta en avlang fylld stapel utanfor planytan och dess delning."""
    diag = sheet.transform.diagonal
    bars = []
    for p in sheet.paths:
        x0, y0, x1, y1 = p.bbox
        w, h = x1 - x0, y1 - y0
        long_side, short_side = max(w, h), min(w, h)
        if short_side <= 0 or long_side / max(short_side, 1e-9) < 20:
            continue
        if long_side < diag * 0.02 or long_side > diag * 0.35:
            continue
        if p.kind not in ("f", "fs"):
            continue
        # Skalstocken ligger normalt i ramzonen. Den far sokas overallt, men
        # stapel utanfor planytan provas forst.
        outside = 0 if (plan is not None and _inside(p.bbox, plan)) else 1
        bars.append((long_side, p, w >= h, outside))
    if not bars:
        return None
    bars.sort(key=lambda b: (-b[3], -b[0]))

    for long_side, bar, horizontal, _outside in bars[:6]:
        bx0, by0, bx1, by1 = bar.bbox
        band = (
            bx0 - long_side * 0.05,
            by0 - long_side * 0.25,
            bx1 + long_side * 0.05,
            by1 + long_side * 0.25,
        )
        axis = 0 if horizontal else 1
        marks = []
        for p in sheet.paths:
            if p.id == bar.id or not _inside(p.bbox, band):
                continue
            px = (p.bbox[0] + p.bbox[2]) / 2 if axis == 0 else (p.bbox[1] + p.bbox[3]) / 2
            marks.append(px)
        if len(marks) < 4:
            continue
        # Delstrecken maste bilda en jamn kam over stapeln. Kammen ar beviset
        # for att den avlanga figuren verkligen ar en skalstock; sjalva skalan
        # rader stapelns *hela* langd over, inte delstreckens antal.
        divisions, coverage = _comb_fit(marks, bx0 if axis == 0 else by0, long_side)
        if divisions == 0 or coverage < 0.8:
            continue
        return ScaleSource(
            "scalebar",
            long_side,
            _candidate_scales(long_side, SCALEBAR_SPAN_MM),
            {
                "bar_len_pt": round(long_side, 2),
                "divisions": divisions,
                "tick_coverage": round(coverage, 3),
                "marks": len(marks),
            },
        )
    return None


def _comb_fit(marks: list[float], start: float, span: float) -> tuple[int, float]:
    """Basta jamna delning av ``span`` som delstrecken i ``marks`` faller pa.

    Returnerar (antal delar, andel gridlinjer som har ett delstreck).
    Foredrar den grovsta delning som fortfarande tacks - annars vinner alltid
    en finare kam.
    """
    best = (0, 0.0)
    for n in range(2, 41):
        pitch = span / n
        hit = 0
        for k in range(n + 1):
            target = start + k * pitch
            if any(abs(m - target) <= pitch * 0.08 for m in marks):
                hit += 1
        cov = hit / (n + 1)
        # Finaste delning som fortfarande ar helt tackt. En grov kam tacks
        # alltid trivialt, sa den sager ingenting om delstrecken.
        if cov >= 0.95 and n > best[0]:
            best = (n, cov)
        elif best[0] == 0 and cov > best[1]:
            best = (n, cov)
    return best


def _inside(box, outer) -> bool:
    return box[0] >= outer[0] and box[1] >= outer[1] and box[2] <= outer[2] and box[3] <= outer[3]


def _max_gap_threshold(values: list[float]) -> float:
    """Troskel dar avstandsfordelningen delar sig kraftigast.

    Glyfstreck inom en siffra ligger tatt; siffror ligger glest. Kvoten mellan
    tva pa varandra foljande sorterade avstand ar storst just dar.
    """
    vs = sorted(values)
    gaps = sorted(g for g in (vs[i + 1] - vs[i] for i in range(len(vs) - 1)) if g > 0)
    if len(gaps) < 2:
        return 0.0
    best_ratio, best = 1.0, gaps[0]
    for i in range(len(gaps) - 1):
        ratio = gaps[i + 1] / gaps[i]
        if ratio > best_ratio:
            best_ratio, best = ratio, math.sqrt(gaps[i] * gaps[i + 1])
    return best


def _cluster_1d(values: list[float], tol: float) -> list[float]:
    vs = sorted(values)
    out: list[list[float]] = [[vs[0]]]
    for v in vs[1:]:
        if v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [statistics.fmean(g) for g in out]


# --------------------------------------------------------------------------
# Kalla 3: vaggtjocklek som rimlighetsgrind


def wall_source(sheet: Sheet, styles) -> tuple[float, list[float]]:
    """Modalt parallellavstand i punkter, over de mest ortogonala klustren."""
    from .styles import orthogonal_share

    cand = [
        c
        for c in styles.clusters
        if c.n_paths >= 20 and orthogonal_share(c) > 0.7 and c.spatial_spread > 0.05
    ]
    cand.sort(key=lambda c: -c.total_length)
    by_id = {p.id: p for p in sheet.paths}
    modes: list[float] = []
    for c in cand[:6]:
        segs = []
        for pid in c.path_ids:
            for a, b in by_id[pid].segments:
                L = math.dist(a, b)
                if L > sheet.transform.diagonal * 1e-3:
                    segs.append((a, b, L, math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi))
        sp = _pair_spacings(segs, sheet.transform.diagonal * 0.012)
        if len(sp) >= 10:
            modes.append(collections.Counter(sp).most_common(1)[0][0])
    return (statistics.median(modes) if modes else 0.0), modes


def _pair_spacings(segs, max_sp: float) -> list[float]:
    out: list[float] = []
    for target in (0.0, math.pi / 2):
        sel = [s for s in segs if min(abs(s[3] - target), math.pi - abs(s[3] - target)) < 0.02]
        axis = 1 if target == 0.0 else 0
        other = 1 - axis
        sel.sort(key=lambda s: s[0][axis])
        for i, s in enumerate(sel):
            for t in sel[i + 1 :]:
                d = abs(t[0][axis] - s[0][axis])
                if d > max_sp:
                    break
                if d <= max_sp * 0.02:
                    continue
                lo = max(min(s[0][other], s[1][other]), min(t[0][other], t[1][other]))
                hi = min(max(s[0][other], s[1][other]), max(t[0][other], t[1][other]))
                if hi - lo > 0.5 * min(s[2], t[2]):
                    out.append(round(d, 1))
    return out


# --------------------------------------------------------------------------


def _snap(scale: float) -> float | None:
    for s in STANDARD_SCALES:
        if abs(scale - s) / s <= 0.02:
            return float(s)
    return None


def determine(
    sheet: Sheet,
    styles=None,
    plan=None,
    tolerance_pct: float = 0.5,
    reference: ScaleReference | None = None,
) -> ScaleResult:
    sources: list[ScaleSource] = []
    flags: list[str] = []

    g = grid_source(sheet)
    if g:
        sources.append(g)
    else:
        flags.append("grid:not_found")

    sb = scalebar_source(sheet, plan)
    if sb:
        sources.append(sb)
    else:
        flags.append("scalebar:not_found")

    # Fjarde kallan: samma skalstock som pa en kalibrerad ritning i projektet.
    # Da ar stapelns verkliga spann kant, och stocken blir en fullvardig
    # geometrisk kalla i stallet for en kandidatlista.
    if reference is not None and reference.matches(sb):
        raw = reference.span_mm * PT_PER_MM / sb.pitch_pt
        snap = _snap(raw)
        if snap is not None:
            sources.append(
                ScaleSource(
                    "project_scalebar",
                    sb.pitch_pt,
                    {snap: raw},
                    {
                        "span_mm": reference.span_mm,
                        "calibrated_on": reference.calibrated_on,
                        "project_key": reference.project_key,
                    },
                )
            )
            flags.append(f"scale_reference:{reference.calibrated_on}")
    elif reference is not None:
        flags.append("scale_reference:scalebar_differs_from_project")

    usable = [s for s in sources if s.ok]
    for s in sources:
        if not s.ok:
            flags.append(f"{s.name}:no_standard_scale")
    if not usable:
        return ScaleResult(None, False, sources, None, flags + ["no_geometric_source"], [])

    # Snittet mellan kallornas kandidatmangder.
    support: dict[float, list[ScaleSource]] = collections.defaultdict(list)
    for s in usable:
        for cand in s.candidates:
            support[cand].append(s)
    max_support = max(len(v) for v in support.values())
    surviving = sorted(sc for sc, v in support.items() if len(v) == max_support)

    # Kalla 3: vaggtjockleken ar en fysisk grind som skiljer decennierna at.
    wall_mode, wall_modes = wall_source(sheet, styles) if styles is not None else (0.0, [])
    if wall_mode > 0:
        plausible = [sc for sc in surviving if WALL_MM_MIN <= wall_mode * MM_PER_PT * sc <= WALL_MM_MAX]
        if plausible:
            if len(plausible) < len(surviving):
                flags.append(
                    "wall_gate_rejected:"
                    + ",".join(f"1:{int(c)}" for c in surviving if c not in plausible)
                )
            surviving = plausible
        else:
            flags.append("wall_gate_rejected_all")
    elif styles is not None:
        flags.append("wall:not_found")

    # R4: en tvetydig skala far ALDRIG loses genom att valja en av dem. Nar
    # flera standardskalor overlever grindarna, eller nar bara en kalla
    # stoder den, ar skalan inte faststalld - och da far ingenting matas.
    ambiguous = len(surviving) > 1
    value = surviving[0]
    used = support[value]
    if wall_mode > 0:
        sources.append(
            ScaleSource(
                "wall",
                wall_mode,
                {value: value},
                {
                    "modal_mm": round(wall_mode * MM_PER_PT * value, 1),
                    "modes_pt": [round(m, 2) for m in wall_modes],
                },
            )
        )

    raw = [s.candidates[value] for s in used]
    error_pct = (max(raw) - min(raw)) / statistics.fmean(raw) * 100 if len(raw) > 1 else None
    verified = len(used) >= 2 and not ambiguous and (error_pct or 0.0) <= tolerance_pct

    if len(used) < 2:
        flags.append("single_source_only")
    if ambiguous:
        flags.append("ambiguous:" + ",".join(f"1:{int(c)}" for c in surviving))
    if error_pct is not None and error_pct > tolerance_pct:
        flags.append(f"sources_disagree:{error_pct:.2f}pct")

    if not verified:
        # Ingen skala levereras. Att lamna ett varde har vore att gissa, och
        # en gissad skala multiplicerar hela mangdforteckningen med fel tal.
        return ScaleResult(None, False, sources, error_pct, flags, surviving)
    return ScaleResult(value, verified, sources, error_pct, flags, surviving)
