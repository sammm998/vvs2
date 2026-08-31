"""Verifierings-PDF: originalet orort, uppmatt geometri i farg ovanpa.

Granskningsregeln star tryckt i legenden:

    originallinje utan farg = missat ror
    farg utan originallinje  = felmatt

Det ar detta en manniska granskar, inte koden. Overlayen ska ga att granska
pa tre minuter per ritning.
"""

from __future__ import annotations

import os

import pymupdf

# Farger per stilkluster, i den ordning klustren kommer.
PALETTE = [
    (0.90, 0.10, 0.10),
    (0.00, 0.60, 0.20),
    (0.10, 0.35, 0.95),
    (0.95, 0.55, 0.00),
    (0.60, 0.10, 0.80),
    (0.00, 0.65, 0.70),
    (0.85, 0.00, 0.55),
    (0.40, 0.45, 0.00),
]
UNLINKED = (0.55, 0.55, 0.55)
VERTICAL = (1.00, 0.00, 0.85)


def render(result, out_path: str, show_blocked: bool = True) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc = pymupdf.open(result.source)
    page = doc[result.sheet.page_number]

    # R8: matningen ligger i normrymden. For att rita in den i kallsidan
    # maste den tillbaka genom transformens invers - annars hamnar overlayen
    # bredvid ritningen sa fort arket har /Rotate.
    tf = result.sheet.transform

    def P(pt) -> pymupdf.Point:
        x, y = tf.invert(pt)
        return pymupdf.Point(x, y)

    colors = {cid: PALETTE[i % len(PALETTE)] for i, cid in enumerate(result.selection.pipe_clusters)}

    # Sparrade banor som eget, slackbart lager.
    if show_blocked:
        ocg_blocked = doc.add_ocg("Sparrade banor", on=False)
        shape = page.new_shape()
        by_id = {p.id: p for p in result.sheet.paths}
        drawn = 0
        for b in result.selection.blocked:
            if b.reason in ("degenerate",):
                continue
            p = by_id.get(b.path_id)
            if not p or p.length <= 0:
                continue
            for a, c in p.segments:
                shape.draw_line(P(a), P(c))
            drawn += 1
            if drawn > 20000:
                break
        shape.finish(color=UNLINKED, width=0.4, stroke_opacity=0.35)
        shape.commit(overlay=True)
        page._set_opacity  # noqa: B018 - hall referensen for tydlighet

    # Uppmatt geometri, ett tandbart lager per stilkluster.
    for cid in result.selection.pipe_clusters:
        strands = [s for s in result.net.strands if s.cluster_id == cid]
        if not strands:
            continue
        layer_name = result.styles.get(cid).key.layer or cid
        ocg = doc.add_ocg(f"Matt: {layer_name}", on=True)
        shape = page.new_shape()
        for s in strands:
            for i in range(len(s.points) - 1):
                shape.draw_line(P(s.points[i]), P(s.points[i + 1]))
        shape.finish(color=colors[cid], width=2.2, stroke_opacity=0.75)
        shape.commit(overlay=True)

    # Vertikala ror
    if result.net.verticals:
        ocg = doc.add_ocg("Vertikala ror", on=True)
        shape = page.new_shape()
        for v in result.net.verticals:
            r = pymupdf.Rect(
                v.center[0] - v.size, v.center[1] - v.size,
                v.center[0] + v.size, v.center[1] + v.size,
            )
            shape.draw_circle(P(v.center), v.size * 1.4)
        shape.finish(color=VERTICAL, width=1.4, stroke_opacity=0.9)
        shape.commit(overlay=True)

    _legend(page, result, colors)
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return out_path


def _legend(page, result, colors) -> None:
    """Legend med granskningsregeln, placerad i en tom del av ramzonen."""
    frame = result.zones.frame
    w, h = 300, 30 + 16 * (len(colors) + 6)
    x0 = frame[0] + 12
    y0 = frame[3] - h - 12
    box = pymupdf.Rect(x0, y0, x0 + w, y0 + h)
    page.draw_rect(box, color=(0, 0, 0), fill=(1, 1, 1), width=0.8, fill_opacity=0.92)

    y = y0 + 16
    page.insert_text((x0 + 8, y), "GRANSKNING AV MATNING", fontsize=9, color=(0, 0, 0))
    y += 13
    page.insert_text((x0 + 8, y), "originallinje utan farg = missat ror", fontsize=7.5)
    y += 10
    page.insert_text((x0 + 8, y), "farg utan originallinje  = felmatt", fontsize=7.5)
    y += 14
    for cid, col in colors.items():
        q = next((q for q in result.quantities if q.cluster_id == cid), None)
        page.draw_line(pymupdf.Point(x0 + 8, y - 3), pymupdf.Point(x0 + 30, y - 3), color=col, width=2.2)
        name = (result.styles.get(cid).key.layer or cid)[-34:]
        txt = f"{name}  {q.length_m:.1f} m" if q else name
        page.insert_text((x0 + 35, y), txt, fontsize=7)
        y += 11
    page.draw_circle(pymupdf.Point(x0 + 19, y - 3), 4, color=VERTICAL, width=1.4)
    page.insert_text((x0 + 35, y), f"vertikala ror: {len(result.net.verticals)} st", fontsize=7)
    y += 12
    sc = result.scale
    page.insert_text(
        (x0 + 8, y),
        f"skala 1:{sc.value:.0f} {'verifierad' if sc.verified else 'OVERIFIERAD'}"
        f"  |  spar {result.triage.track}  |  total {result.total_length_m:.1f} m",
        fontsize=7,
    )
    y += 11
    if result.flags or result.selection.flags:
        flags = ", ".join((result.flags + result.selection.flags)[:3])
        page.insert_text((x0 + 8, y), f"flaggor: {flags[:60]}", fontsize=6.5, color=(0.7, 0, 0))
