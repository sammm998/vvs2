"""R9 - ingen optimering utan matning fore och efter.

``evaluate`` kor hela facituppsattningen och skriver matten till eval_results
med tidsstampel och git-sha. Varje fas lagger till matt i samma funktion:

    fas 1   tackning, banor per spar
    fas 2   antal stilkluster, andel i de tre storsta
    fas 3   skala hittad vs facit, procentuellt fel, verifierad
    fas 4   andel geometri i exkluderingszoner
    fas 6   rorstilsklustrets totala langd
    fas 7   total langd vs facit, noder, vertikala vs facit, plataabredd
    fas 8   MAPE per beteckning, andel okopplat
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from . import db, groundtruth, pipeline


@dataclass
class Evaluation:
    drawing: str
    metrics: dict

    def print_report(self) -> None:
        m = self.metrics
        print(f"\n{'=' * 72}\n{self.drawing}\n{'=' * 72}")
        _line("spar", m.get("track"))
        _line("tackning (R6)", f"{m['coverage']:.4f}", ok=abs(m["coverage"] - 1.0) < 1e-9)
        _line("banor", m["n_paths"])
        _line("stilkluster", m["n_clusters"])
        _line("andel i 3 storsta", f"{m['share_top3']:.1%}")
        _line("geometri i exkluderingszon", f"{m['share_in_excluded']:.1%}")
        sc = m["scale"]
        _line("skala", f"1:{sc['value']:.0f} verifierad={sc['verified']} fel={sc['error_pct']}%", ok=sc["verified"])
        _line("rorstilskluster", m["n_pipe_clusters"])
        _line("rorstil raalangd", f"{m['pipe_raw_length_m']:.1f} m")
        _line("plataabredd (min)", f"{m['min_plateau_width']:.2f}")
        _line("noder", m["n_nodes"])
        _line("strak", m["n_strands"])
        if m.get("facit") is None:
            print("  (inget facit for denna ritning - generaliseringstest)")
            return
        f = m["facit"]
        _line("TOTAL LANGD", f"{m['total_length_m']:.1f} m mot facit {f['total_length_m']:.1f} m "
                            f"({m['length_error_pct']:+.1f}%)", ok=abs(m["length_error_pct"]) <= 10)
        _line("i facitomfang", f"{m['in_scope_length_m']:.1f} m ({m['in_scope_error_pct']:+.1f}%)",
              ok=abs(m["in_scope_error_pct"]) <= 10)
        _line("utanfor facitomfang", f"{m['out_of_scope_length_m']:.1f} m ({m['out_of_scope_note']})")
        _line("i maskad zon (ej mangd)", f"{m['masked_length_m']:.1f} m, "
                                          f"{m['masked_verticals']} vertikala")
        _line("vertikala ror", f"{m['n_verticals']} mot facit {f['total_verticals']:.0f} "
                               f"({m['vertical_error']:+.0f})", ok=abs(m["vertical_error"]) <= 10)
        _line("noder < 3x beteckningar", f"{m['n_nodes']} vs {3 * f['n_labels']}",
              ok=m["n_nodes"] < 3 * f["n_labels"])
        if m.get("per_system"):
            print("\n  per stilkluster (systemniva):")
            print(f"    {'matt_m':>8} {'facit_m':>8} {'fel':>8}  lager")
            for row in m["per_system"]:
                fe = f"{row['error_pct']:+7.1f}%" if row["error_pct"] is not None else "      -"
                print(f"    {row['length_m']:8.1f} {row['facit_m'] or 0:8.1f} {fe}  {row['layer']}")
            if m.get("system_mape") is not None:
                _line("MAPE per system", f"{m['system_mape']:.1f}%", ok=m["system_mape"] <= 10)


def _line(name: str, value, ok: bool | None = None) -> None:
    mark = "" if ok is None else ("  OK" if ok else "  <-- UNDER GRIND")
    print(f"  {name:<28} {value}{mark}")


def evaluate(
    result: pipeline.RunResult,
    gt: groundtruth.GroundTruth | None = None,
    layer_scope: dict[str, str] | None = None,
) -> Evaluation:
    """Berakna alla matt for en korning.

    ``layer_scope`` avgor vilka stilkluster som ingar i facitets omfang.
    Kluster utanfor omfanget mats anda och redovisas som egen rad - de
    tystas aldrig (R10).
    """
    r = result
    clusters = r.styles.clusters
    total_len = sum(c.total_length for c in clusters) or 1.0
    top3 = sum(sorted((c.total_length for c in clusters), reverse=True)[:3])

    excluded_len = 0.0
    for p in r.sheet.paths:
        if r.zones.classify(p.bbox) != "plan":
            excluded_len += p.length

    plateaus = [cr.plateau_width for cr in r.chains.values()] or [0.0]

    m: dict = {
        "track": r.triage.track,
        "n_paths": len(r.sheet.paths),
        "coverage": r.coverage,
        "n_clusters": len(clusters),
        "share_top3": top3 / total_len,
        "share_in_excluded": excluded_len / total_len,
        "scale": r.scale.as_dict(),
        "n_pipe_clusters": len(r.selection.pipe_clusters),
        "pipe_raw_length_m": sum(q.raw_length_m for q in r.quantities),
        "min_plateau_width": min(plateaus),
        "n_nodes": len(r.net.nodes),
        "n_strands": len(r.net.strands),
        "n_verticals": len(r.net.verticals),
        "total_length_m": r.total_length_m,
        "masked_length_m": r.masked_length_m,
        "masked_verticals": r.masked_verticals,
        "method": r.selection.method,
        "flags": r.flags + r.selection.flags + r.scale.flags,
        "facit": None,
    }

    if gt is None:
        return Evaluation(r.drawing, m)

    tot = gt.totals()
    m["facit"] = {
        "total_length_m": tot["total_length_m"],
        "total_verticals": tot["total_verticals"],
        "n_labels": len(tot["labels"]),
        "labels": tot["labels"],
    }

    # Omfang: vilka kluster ingar i facitet? Ovriga mats men redovisas separat.
    scope = layer_scope or {}
    in_scope = [q for q in r.quantities if scope.get(q.layer or "", "in") != "out"]
    out_scope = [q for q in r.quantities if scope.get(q.layer or "", "in") == "out"]
    m["in_scope_length_m"] = sum(q.length_m for q in in_scope)
    m["out_of_scope_length_m"] = sum(q.length_m for q in out_scope)
    m["out_of_scope_note"] = (
        ", ".join(f"{q.layer}" for q in out_scope) or "inga"
    )
    fl = tot["total_length_m"] or 1.0
    m["length_error_pct"] = (m["total_length_m"] - fl) / fl * 100
    m["in_scope_error_pct"] = (m["in_scope_length_m"] - fl) / fl * 100
    m["vertical_error"] = len(r.net.verticals) - tot["total_verticals"]

    # Per stilkluster mot facit, nar en kluster->facit-koppling finns.
    per_system = []
    errs = []
    facit_by_layer = (layer_scope or {}).get("__facit_by_layer__") if layer_scope else None
    for q in sorted(r.quantities, key=lambda q: -q.length_m):
        fm = None
        if isinstance(facit_by_layer, dict):
            fm = facit_by_layer.get(q.layer or "")
        err = None if not fm else (q.length_m - fm) / fm * 100
        if err is not None:
            errs.append(abs(err))
        per_system.append(
            {"layer": q.layer, "length_m": q.length_m, "facit_m": fm, "error_pct": err}
        )
    m["per_system"] = per_system
    m["system_mape"] = statistics.fmean(errs) if errs else None
    return Evaluation(r.drawing, m)


def facit_scope(
    result: pipeline.RunResult,
    geometry: list[dict],
    tol_units: float = 2.0,
    clusters: list[str] | None = None,
) -> dict:
    """Harled vilka stilkluster facitet faktiskt omfattar, ur dess geometri.

    For varje facitpolylinje soks det stilkluster vars banor ligger narmast.
    Kluster som ingen facitlinje pekar pa ligger *utanfor* facitets omfang -
    de mats anda och redovisas som egen rad, aldrig som fel (R10).

    Ingen lagernamnslista hardkodas; kopplingen kommer ur geometrin.
    """
    by_id = {p.id: p for p in result.sheet.paths}
    # Vilka kluster som far ta emot facitgeometri. Vid kalibrering maste ALLA
    # kluster vara med: att bara erbjuda dem som rorurvalet redan godkant vore
    # cirkulart och skulle dolja precis de lager urvalet missade.
    pool = clusters if clusters is not None else result.selection.pipe_clusters
    unit = statistics.median(
        [result.styles.get(c).width for c in result.selection.pipe_clusters]
    ) if result.selection.pipe_clusters else result.sheet.epsilon()
    tol = unit * tol_units

    # Rutnat over rorklustrens segment
    cell = max(tol * 6, 1e-6)
    grid: dict[tuple[int, int], list[tuple[str, tuple, tuple]]] = {}
    for cid in pool:
        for pid in result.styles.get(cid).path_ids:
            for a, b in by_id[pid].segments:
                if math.dist(a, b) <= 0:
                    continue
                x0, x1 = sorted((a[0], b[0]))
                y0, y1 = sorted((a[1], b[1]))
                for gx in range(int(x0 // cell), int(x1 // cell) + 1):
                    for gy in range(int(y0 // cell), int(y1 // cell) + 1):
                        grid.setdefault((gx, gy), []).append((cid, a, b))

    def nearest_cluster(p):
        gx, gy = int(p[0] // cell), int(p[1] // cell)
        best = (float("inf"), None)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for cid, a, b in grid.get((gx + i, gy + j), ()):
                    d = _pt_seg(p, a, b)
                    if d < best[0]:
                        best = (d, cid)
        return best

    facit_by_cluster: dict[str, float] = {}
    label_by_cluster: dict[str, set] = {}
    m_per_pt = result.scale.m_per_pt
    for g in geometry:
        if g["is_vertical"] or g["length_pt"] <= 0:
            continue
        v = g["vertices"]
        votes: dict[str, float] = {}
        for i in range(len(v) - 1):
            L = math.dist(v[i], v[i + 1])
            if L <= 0:
                continue
            n = max(2, int(L / max(tol, 1e-6)))
            for k in range(n + 1):
                t = k / n
                p = (v[i][0] + (v[i + 1][0] - v[i][0]) * t, v[i][1] + (v[i + 1][1] - v[i][1]) * t)
                d, cid = nearest_cluster(p)
                if cid is not None and d <= tol:
                    # Avstandsviktad rost: ett kluster som ligger RAKT under
                    # facitlinjen vager tyngre an ett som bara ryms inom
                    # toleransen. Utan vikten vinner ibland en underlagslinje
                    # som rakar folja roret en bit.
                    votes[cid] = votes.get(cid, 0.0) + (L / (n + 1)) / (1.0 + d)
        if not votes:
            continue
        cid = max(votes, key=votes.get)
        # Facitlinjen ritades OVANPA ledningen. Bar det narmaste klustret
        # bara en liten del av den ar traffen en tillfallighet - typiskt en
        # beteckningstext eller ett underlag som rakar folja roret en bit -
        # och far inte gora det klustret till ett ledningslager.
        if votes[cid] < g["length_pt"] * 0.35:
            continue
        facit_by_cluster[cid] = facit_by_cluster.get(cid, 0.0) + g["length_pt"] * m_per_pt
        label_by_cluster.setdefault(cid, set()).add(g["label"])

    scope: dict[str, str] = {}
    facit_by_layer: dict[str, float] = {}
    for q in result.quantities:
        cid = q.cluster_id
        if cid in facit_by_cluster:
            scope[q.layer or ""] = "in"
            facit_by_layer[q.layer or ""] = facit_by_cluster[cid]
        else:
            scope[q.layer or ""] = "out"
    scope["__facit_by_layer__"] = facit_by_layer
    scope["__labels_by_cluster__"] = {k: sorted(v) for k, v in label_by_cluster.items()}
    return scope


def _pt_seg(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def save(ev: Evaluation, run_id: int | None = None, path: str = db.DEFAULT_PATH) -> int:
    con = db.connect(path)
    try:
        return db.save_eval(con, run_id, ev.drawing, ev.metrics)
    finally:
        con.close()
