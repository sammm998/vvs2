"""Fas 0 - triage-probe. Engangsskript, ingen abstraktion.

Svarar pa de fem fragorna i FASER.md mot en eller flera PDF:er och skriver
svaren rakt i terminalen. Renderar ett klusteroverlay per stilkluster till
out/probe/.

    python scratch/probe.py data/W501A0011-single.pdf
"""

from __future__ import annotations

import collections
import math
import os
import sys

import pymupdf

PT_PER_MM = 72.0 / 25.4


def path_length(item) -> float:
    tot = 0.0
    for x in item["items"]:
        if x[0] == "l":
            tot += abs(x[1] - x[2])
        elif x[0] == "c":
            pts = [x[1], x[2], x[3], x[4]]
            tot += sum(abs(pts[i] - pts[i + 1]) for i in range(3))
        elif x[0] == "re":
            tot += 2 * (x[1].width + x[1].height)
        elif x[0] == "qu":
            q = x[1]
            tot += abs(q.ul - q.ur) + abs(q.ur - q.lr) + abs(q.lr - q.ll) + abs(q.ll - q.ul)
    return tot


def dash_signature(dashes: str) -> str:
    """Normaliserad strecksignatur, oberoende av absolut skala."""
    if not dashes or dashes.strip() in ("[] 0", "[]0"):
        return "solid"
    inner = dashes[dashes.find("[") + 1 : dashes.find("]")]
    try:
        terms = [float(t) for t in inner.split()]
    except ValueError:
        return f"raw:{dashes}"
    if not terms:
        return "solid"
    period = sum(terms) or 1.0
    norm = "/".join(f"{t / period:.2f}" for t in terms)
    return f"n{len(terms)}:{norm}"


def quant_color(c, step=0.08):
    if c is None:
        return None
    return tuple(round(v / step) * step for v in c)


def style_key(item):
    stroke = item.get("color") if item.get("type") in ("s", "fs") else None
    return (
        quant_color(stroke),
        quant_color(item.get("fill")),
        round(item.get("width") or 0.0, 2),
        dash_signature(item.get("dashes") or ""),
        item.get("layer"),
    )


def q1_layers(doc, page, drawings):
    print("\n" + "=" * 78)
    print("FRAGA 1 - OCG-lager")
    print("=" * 78)
    ocgs = doc.get_ocgs()
    if not ocgs:
        print("  INGA OCG-lager. Spar B.")
        return
    per = collections.Counter(d.get("layer") for d in drawings)
    print(f"  {len(ocgs)} OCG:er deklarerade, {len(per)} med banor pa sidan.")
    print(f"  {'banor':>7}  {'langd_m':>9}  lager")
    lens = collections.Counter()
    for d in drawings:
        lens[d.get("layer")] += path_length(d)
    for name, n in per.most_common():
        print(f"  {n:7d}  {lens[name] * M_PER_PT:9.1f}  {name!r}")
    unassigned = per.get(None, 0)
    print(f"  banor utan lager: {unassigned}")


def q2_text(page, drawings):
    print("\n" + "=" * 78)
    print("FRAGA 2 - riktig PDF-text")
    print("=" * 78)
    words = page.get_text("words")
    print(f"  {len(words)} textord i hela sidan.")
    plan = plan_rect(page, drawings)
    print(f"  storsta inramade tomma ytan (planyta): {plan}")
    inside = [w for w in words if pymupdf.Rect(w[:4]) in plan]
    frac = len(inside) / len(words) if words else 0.0
    print(f"  {len(inside)} av {len(words)} ord innanfor planytan ({frac:.0%}).")
    if len(inside) < 50:
        print("  => Ritningens text ar vektoriserad (SHX). Glyfklustring + vision kravs.")
    else:
        print("  => Riktig text i planytan raknas som anvandbar.")
    for w in words:
        print(f"     {w[4]!r} @ ({w[0]:.0f},{w[1]:.0f})")


def plan_rect(page, drawings):
    """Grov topologisk planyta: median-tathetsomrade av all geometri.

    Probe-kvalitet. Riktig harledning sker i zones.py.
    """
    xs = sorted(d["rect"].x0 for d in drawings) + sorted(d["rect"].x1 for d in drawings)
    ys = sorted(d["rect"].y0 for d in drawings) + sorted(d["rect"].y1 for d in drawings)
    if not xs:
        return page.rect

    def pct(v, p):
        return v[max(0, min(len(v) - 1, int(len(v) * p)))]

    return pymupdf.Rect(pct(xs, 0.02), pct(ys, 0.02), pct(xs, 0.98), pct(ys, 0.98))


def q3_styles(drawings):
    print("\n" + "=" * 78)
    print("FRAGA 3 - stilinventering")
    print("=" * 78)
    clusters = collections.defaultdict(list)
    for i, d in enumerate(drawings):
        clusters[style_key(d)].append(i)
    lens = {k: sum(path_length(drawings[i]) for i in v) for k, v in clusters.items()}
    total = sum(lens.values()) or 1.0
    order = sorted(clusters, key=lambda k: -lens[k])
    print(f"  {len(clusters)} stilkluster. Totallangd {total * M_PER_PT:.0f} m @ {SCALE_TXT}.")
    print(f"  {'#':>3} {'banor':>6} {'langd_m':>9} {'andel':>6}  stroke / bredd / streck / lager")
    for i, k in enumerate(order):
        stroke, fill, w, dash, layer = k
        sc = "-" if stroke is None else ",".join(f"{v:.2f}" for v in stroke)
        share = lens[k] / total
        print(
            f"  {i:3d} {len(clusters[k]):6d} {lens[k] * M_PER_PT:9.1f} {share:6.1%}  "
            f"({sc}) w={w:.2f} {dash} L={layer!r}"
        )
    return order, clusters


def q4_overlays(page, drawings, order, clusters, outdir, top=24):
    print("\n" + "=" * 78)
    print("FRAGA 4 - klusteroverlays")
    print("=" * 78)
    os.makedirs(outdir, exist_ok=True)
    palette = [(1, 0, 0), (0, 0.6, 0), (0, 0.3, 1), (1, 0.5, 0), (0.7, 0, 0.9), (0, 0.7, 0.7)]
    zoom = 1400 / max(page.rect.width, page.rect.height)
    mat = pymupdf.Matrix(zoom, zoom)
    for i, k in enumerate(order[:top]):
        doc2 = pymupdf.open()
        doc2.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
        pg = doc2[0]
        shape = pg.new_shape()
        col = palette[i % len(palette)]
        for idx in clusters[k]:
            r = drawings[idx]["rect"] + (-2, -2, 2, 2)
            shape.draw_rect(r)
        shape.finish(color=col, width=1.5, fill=col, fill_opacity=0.35, stroke_opacity=0.9)
        shape.commit()
        name = f"{outdir}/cluster_{i:02d}.png"
        pg.get_pixmap(matrix=mat).save(name)
        doc2.close()
        print(f"  skrev {name}  ({len(clusters[k])} banor, lager={k[4]!r})")


def q5_scalebar(page, drawings):
    print("\n" + "=" * 78)
    print("FRAGA 5 - skalstock")
    print("=" * 78)
    words = page.get_text("words")
    nums = []
    for w in words:
        t = w[4].replace(",", ".")
        try:
            nums.append((float(t), pymupdf.Rect(w[:4])))
        except ValueError:
            pass
    if not nums:
        print("  inga numeriska etiketter alls.")
        return
    rows = collections.defaultdict(list)
    for v, r in nums:
        rows[round(r.y0 / 10)].append((v, r))
    best = None
    for _, group in rows.items():
        if len(group) < 3:
            continue
        group.sort(key=lambda g: g[1].x0)
        vals = [g[0] for g in group]
        cx = [(g[1].x0 + g[1].x1) / 2 for g in group]
        dv = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
        dx = [cx[i + 1] - cx[i] for i in range(len(cx) - 1)]
        if min(dv) <= 0 or min(dx) <= 0:
            continue
        ratios = [dx[i] / dv[i] for i in range(len(dv))]
        spread = (max(ratios) - min(ratios)) / (sum(ratios) / len(ratios))
        if best is None or spread < best[0]:
            best = (spread, group, ratios)
    if best is None:
        print("  hittade ingen rad med >=3 stigande sifferetiketter.")
        return
    spread, group, ratios = best
    print("  kandidatrad (regelbundna sifferetiketter):")
    for v, r in group:
        print(f"     {v:g} @ x={(r.x0 + r.x1) / 2:.1f} y={r.y0:.1f}")
    pt_per_unit = sum(ratios) / len(ratios)
    print(f"  pt per etikettenhet: {pt_per_unit:.3f}  (spridning mellan steg {spread:.2%})")
    for unit_mm, label in ((100.0, "dm"), (1000.0, "m"), (10.0, "cm")):
        scale = unit_mm * PT_PER_MM / pt_per_unit
        print(f"     om etiketterna ar {label}: skala 1:{scale:.2f}")
    ticks = [
        d
        for d in drawings
        if d["rect"].y0 > group[0][1].y0 - 60
        and d["rect"].y1 < group[0][1].y1 + 60
        and d["rect"].width < 40
    ]
    print(f"  {len(ticks)} smala vektorobjekt (delstreck) i etiketternas zon.")


if __name__ == "__main__":
    paths = sys.argv[1:] or ["data/W501A0011-single.pdf"]
    for pdf in paths:
        doc = pymupdf.open(pdf)
        page = doc[0]
        drawings = page.get_drawings()
        # Skalan ar inte harledd an i fas 0; 1:50 anvands som visningsenhet
        # och verifieras av fraga 5.
        SCALE_TXT = "1:50"
        M_PER_PT = 25.4 / 72 / 1000 * 50
        print("\n" + "#" * 78)
        print(f"# {pdf}")
        print(f"# sida 0: rect={page.rect} rotate={page.rotation} banor={len(drawings)}")
        print("#" * 78)
        q1_layers(doc, page, drawings)
        q2_text(page, drawings)
        order, clusters = q3_styles(drawings)
        stem = os.path.splitext(os.path.basename(pdf))[0]
        q4_overlays(page, drawings, order, clusters, f"out/probe/{stem}")
        q5_scalebar(page, drawings)
        doc.close()
