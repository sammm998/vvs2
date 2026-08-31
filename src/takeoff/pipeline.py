"""Hela kedjan: extraktion -> stil -> zoner -> skala -> rorval -> nat -> mangd.

Ordningen ar den i CLAUDE.md. Tackningen (R6) kontrolleras efter varje steg
som kan sparra banor.
"""

from __future__ import annotations

import math
import os
import statistics
from dataclasses import dataclass, field

from . import chain, extract, layergrammar, network, pipes, scale, styles, zones
from .triage import triage, TriageResult

M_PER_MM = 1 / 1000.0


@dataclass
class SystemQuantity:
    cluster_id: str
    layer: str | None
    length_m: float
    raw_length_m: float
    masked_length_m: float
    strands: int
    verticals: int
    masked_verticals: int
    bends: int
    flags: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    drawing: str
    source: str
    sheet: extract.Sheet
    triage: TriageResult
    styles: styles.StyleIndex
    zones: zones.ZoneMap
    scale: scale.ScaleResult
    selection: pipes.PipeSelection
    chains: dict[str, chain.ChainResult]
    net: network.Network
    quantities: list[SystemQuantity]
    flags: list[str] = field(default_factory=list)

    @property
    def total_length_m(self) -> float:
        return sum(q.length_m for q in self.quantities)

    @property
    def masked_verticals(self) -> int:
        """Vertikala ror i maskad zon. Redovisas, ingar inte i antalet (R10)."""
        return sum(q.masked_verticals for q in self.quantities)

    @property
    def masked_length_m(self) -> float:
        """Langd i maskad zon. Redovisas, ingar inte i mangden (R10)."""
        return sum(q.masked_length_m for q in self.quantities)

    @property
    def coverage(self) -> float:
        accepted = sum(len(self.styles.get(c).path_ids) for c in self.selection.pipe_clusters)
        return (accepted + len(self.selection.blocked)) / max(len(self.sheet.paths), 1)

    def summary(self) -> dict:
        return {
            "drawing": self.drawing,
            "track": self.triage.track,
            "paths": len(self.sheet.paths),
            "coverage": round(self.coverage, 4),
            "scale": self.scale.as_dict(),
            "pipe_clusters": len(self.selection.pipe_clusters),
            "method": self.selection.method,
            "total_length_m": round(self.total_length_m, 1),
            "masked_length_m": round(self.masked_length_m, 1),
            "strands": len(self.net.strands),
            "nodes": len(self.net.nodes),
            "verticals": len(self.net.verticals),
            "flags": self.flags + self.selection.flags + self.scale.flags,
            "systems": [
                {
                    "cluster": q.cluster_id,
                    "layer": q.layer,
                    "length_m": round(q.length_m, 1),
                    "raw_length_m": round(q.raw_length_m, 1),
                    "masked_length_m": round(q.masked_length_m, 1),
                    "strands": q.strands,
                    "verticals": q.verticals,
                    "masked_verticals": q.masked_verticals,
                    "bends": q.bends,
                }
                for q in sorted(self.quantities, key=lambda q: -q.length_m)
            ],
        }


def run(
    source: str,
    drawing: str | None = None,
    page: int = 0,
    layer_rule=None,
) -> RunResult:
    sheet = extract.load(source, page)
    tri = triage(sheet)
    style_index = styles.build(sheet)
    zonemap = zones.detect(sheet)
    # R2: projektprofilen far ateranvandas inom samma projekt, aldrig mellan.
    pkey = layergrammar.project_key(sheet.layers)
    sc = scale.determine(
        sheet,
        style_index,
        zonemap.plan,
        reference=layergrammar.load_project_scale(pkey),
    )
    flags: list[str] = []
    if not sc.verified:
        flags.append("scale_unverified:preliminary_quantities")
    if sc.value is None:
        raise RuntimeError(
            "Skalan kunde inte faststallas geometriskt. Matning avbryts (R4). "
            f"Flaggor: {sc.flags}"
        )

    if layer_rule is None:
        layer_rule = layergrammar.load_project_rule(pkey)
    selection = pipes.classify(sheet, style_index, zonemap, sc, layer_rule=layer_rule)
    by_id = {p.id: p for p in sheet.paths}

    # Sammanfogning per stilkluster - aldrig over stilgranser (R7).
    chains: dict[str, chain.ChainResult] = {}
    runs_by_cluster: dict[str, list[chain.Run]] = {}
    for cid in selection.pipe_clusters:
        paths = [by_id[pid] for pid in style_index.get(cid).path_ids]
        cr = chain.build(sheet, paths)
        chains[cid] = cr
        runs_by_cluster[cid] = cr.runs
        if cr.plateau_width <= 0:
            flags.append(f"chain:{cid}:no_plateau")

    pipe_widths = [style_index.get(c).width for c in selection.pipe_clusters]
    unit = statistics.median(pipe_widths) if pipe_widths else sheet.epsilon()

    net = network.build(runs_by_cluster, eps=unit)

    # Fas 4: schrafferad zon = omrade ritningen sjalv undantar. Ledningar dar
    # mats, men redovisas separat och gar inte in i mangden (R10).
    mask = zones.hatch_mask(sheet, style_index, selection, zonemap)
    if mask:
        flags.append(f"masked_zone:{len(mask.clusters)}_hatch_clusters")

    # Vertikala ror: sma symboler pa rorlagren som inte sjalva ar rorstil.
    pipe_layers = {style_index.get(c).key.layer for c in selection.pipe_clusters}
    pipe_pids = {pid for c in selection.pipe_clusters for pid in style_index.get(c).path_ids}
    cand = [
        p
        for p in sheet.paths
        if p.layer in pipe_layers and p.id not in pipe_pids and p.length > 0
    ]
    cluster_of_layer = {style_index.get(c).key.layer: c for c in selection.pipe_clusters}
    network.find_verticals(net, cand, cluster_of_layer, unit)
    # Samma omfangsregel som for langden: en stigarsymbol i en maskad zon
    # hor till det omrade ritningen undantar och raknas darfor inte in.
    # Att mata langden med en regel och antalet med en annan vore ohallbart.
    net.masked_verticals = [v for v in net.verticals if mask.contains(v.center)]
    net.verticals = [v for v in net.verticals if not mask.contains(v.center)]

    quantities = _quantify(sc, style_index, selection, chains, net, mask)
    return RunResult(
        drawing=drawing or os.path.splitext(os.path.basename(source))[0],
        source=source,
        sheet=sheet,
        triage=tri,
        styles=style_index,
        zones=zonemap,
        scale=sc,
        selection=selection,
        chains=chains,
        net=net,
        quantities=quantities,
        flags=flags,
    )


def _masked_split(strands, mask) -> tuple[float, float]:
    """Dela strakens langd i (utanfor mask, i mask)."""
    outside = inside = 0.0
    for s in strands:
        for i in range(len(s.points) - 1):
            a, b = s.points[i], s.points[i + 1]
            L = math.dist(a, b)
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if mask is not None and mask.contains(mid):
                inside += L
            else:
                outside += L
    return outside, inside


def _quantify(sc, style_index, selection, chains, net, mask=None) -> list[SystemQuantity]:
    out: list[SystemQuantity] = []
    for cid in selection.pipe_clusters:
        c = style_index.get(cid)
        strands = [s for s in net.strands if s.cluster_id == cid]
        verts = [v for v in net.verticals if v.cluster_id == cid]
        masked_verts = [v for v in net.masked_verticals if v.cluster_id == cid]
        cr = chains[cid]
        f = []
        if cr.plateau_width <= 0:
            f.append("no_plateau")
        if not sc.verified:
            f.append("scale_unverified")
        if selection.method == "structural":
            f.append("style_by_structure_not_anchor")
        outside_pt, inside_pt = _masked_split(strands, mask)
        if inside_pt > 0:
            f.append("length_in_masked_zone_excluded")
        out.append(
            SystemQuantity(
                cluster_id=cid,
                layer=c.key.layer,
                length_m=sc.to_m(outside_pt),
                raw_length_m=sc.to_m(c.total_length),
                masked_length_m=sc.to_m(inside_pt),
                strands=len(strands),
                verticals=len(verts),
                masked_verticals=len(masked_verts),
                bends=max(0, len(strands) - 1),
                flags=f,
            )
        )
    return out
