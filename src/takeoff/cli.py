"""Kommandoradsgranssnitt.

    takeoff triage    <pdf>            Spar A/B/C + inventering
    takeoff profile   <pdf>            Harled och spara projektprofil
    takeoff run       <pdf>            Hela kedjan -> resultat i SQLite
    takeoff overlay   <pdf>            Verifierings-PDF till out/
    takeoff import-facit <xlsx>        Las facit till ground_truth
    takeoff evaluate  [--all]          Diff mot facit, skriver till eval_results
    takeoff compare   <run_a> <run_b>  Forbattrade andringen resultatet?
"""

from __future__ import annotations

import glob
import json
import os

import typer

from . import db, evaluate as ev, extract, groundtruth, overlay as ov, pipeline, profile as prof
from . import styles as st
from . import zones as zn

app = typer.Typer(add_completion=False, help=__doc__)

DATA_GLOB = "data/*.pdf"


def _drawing_name(pdf: str) -> str:
    return os.path.splitext(os.path.basename(pdf))[0]


def _facit_for(drawing: str) -> tuple[str | None, str | None]:
    """Hitta facit-xlsx och eventuell uppmarkt PDF for en ritning."""
    stem = drawing.replace("-single", "").replace("-bundle", "")
    xlsx = next(iter(glob.glob(f"data/{stem}*.xlsx")), None)
    marked = next(iter(glob.glob(f"data/{stem}*bundle*.pdf")), None)
    return xlsx, marked


@app.command()
def triage(pdf: str) -> None:
    """Spar A/B/C + inventering av lager, farger, linjetyper och zoner."""
    sheet = extract.load(pdf)
    zonemap = zn.detect(sheet)
    from .triage import triage as do

    res = do(sheet, zonemap.plan)
    print(json.dumps(res.as_dict(), indent=2, ensure_ascii=False))
    print("\nzoner:")
    print(json.dumps(zonemap.as_dict(), indent=2, ensure_ascii=False))


@app.command()
def profile(pdf: str) -> None:
    """Harled och spara projektprofilen."""
    result = pipeline.run(pdf)
    p = prof.derive(result)
    path = prof.save(p)
    print(f"skrev {path}")
    print(json.dumps({k: p[k] for k in ("track", "scale", "pipe_representation", "status_rule")},
                     indent=2, ensure_ascii=False))


@app.command()
def run(pdf: str, save_profile: bool = True) -> None:
    """Hela kedjan. Resultatet skrivs till SQLite och sammanfattas."""
    result = pipeline.run(pdf)
    print(json.dumps(result.summary(), indent=2, ensure_ascii=False))
    con = db.connect()
    try:
        cur = con.execute(
            "INSERT INTO runs (drawing, source, started_at, git_sha, track, scale_value, scale_verified, profile_json)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (result.drawing, result.source, db.now(), db.git_sha(), result.triage.track,
             result.scale.value, int(result.scale.verified), json.dumps(result.summary(), ensure_ascii=False)),
        )
        run_id = cur.lastrowid
        con.executemany(
            "INSERT INTO blocked_paths VALUES (?,?,?,?,?)",
            [(run_id, b.path_id, b.cluster_id, b.reason, b.step) for b in result.selection.blocked],
        )
        con.executemany(
            "INSERT INTO strands (run_id, strand_id, cluster_id, length_pt, length_m, label, label_source, points_json)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [(run_id, s.id, s.cluster_id, s.length, result.scale.to_m(s.length), None, "none",
              json.dumps([[round(x, 2), round(y, 2)] for x, y in s.points]))
             for s in result.net.strands],
        )
        con.executemany(
            "INSERT INTO quantities VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(run_id, q.layer, q.layer, None, q.length_m, q.verticals, q.bends, 0, "unsplit",
              ",".join(q.flags)) for q in result.quantities],
        )
        con.commit()
        print(f"\nkorning {run_id} sparad i {db.DEFAULT_PATH}")
    finally:
        con.close()
    if save_profile:
        print("profil:", prof.save(prof.derive(result)))


@app.command()
def overlay(pdf: str, out: str = "") -> None:
    """Verifierings-PDF till out/."""
    result = pipeline.run(pdf)
    target = out or f"out/overlay_{result.drawing}.pdf"
    print("skrev", ov.render(result, target))


@app.command("import-facit")
def import_facit(xlsx: str, drawing: str = "") -> None:
    """Las facit ur Excel. Omimport raderar tidigare facit for ritningen."""
    gt = groundtruth.load_excel(xlsx, drawing or None)
    con = db.connect()
    try:
        n = db.replace_ground_truth(con, gt)
    finally:
        con.close()
    print(f"\nimporterade {n} facitrader for {gt.drawing!r}")
    print(json.dumps(gt.totals(), indent=2, ensure_ascii=False))


@app.command()
def evaluate(pdf: str = "", all: bool = False) -> None:
    """Diff mot facit. Skriver till eval_results."""
    targets = sorted(glob.glob(DATA_GLOB)) if all else ([pdf] if pdf else [])
    if not targets:
        raise typer.BadParameter("ange en PDF eller --all")
    # Uppmarkta facitfiler ar inte matobjekt.
    targets = [t for t in targets if "bundle" not in os.path.basename(t)]
    for t in targets:
        result = pipeline.run(t)
        drawing = _drawing_name(t)
        xlsx, marked = _facit_for(drawing)
        gt = None
        scope = None
        if xlsx:
            gt = groundtruth.load_excel(xlsx, drawing, verbose=False)
            if marked:
                geom = groundtruth.load_markup_geometry(marked)
                scope = ev.facit_scope(result, geom)
        evaluation = ev.evaluate(result, gt, scope)
        evaluation.print_report()
        ev.save(evaluation)


@app.command()
def compare(run_a: int, run_b: int) -> None:
    """Vad gjorde andringen? Sorterat pa storsta forsamring forst."""
    con = db.connect()
    try:
        rows = {}
        for rid, tag in ((run_a, "a"), (run_b, "b")):
            for label, length in con.execute(
                "SELECT label, length_m FROM quantities WHERE run_id = ?", (rid,)
            ):
                rows.setdefault(label, {})[tag] = length
    finally:
        con.close()
    diffs = []
    for label, v in rows.items():
        a, b = v.get("a"), v.get("b")
        diffs.append((label, a, b, (b or 0) - (a or 0)))
    diffs.sort(key=lambda d: d[3])
    print(f"{'label':<44} {'run_a':>9} {'run_b':>9} {'diff':>9}")
    for label, a, b, d in diffs:
        print(f"{str(label):<44} {a if a is not None else float('nan'):9.1f} "
              f"{b if b is not None else float('nan'):9.1f} {d:+9.1f}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
