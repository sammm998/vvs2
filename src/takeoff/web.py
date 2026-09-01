"""Webbtjanst: ladda upp en ritning, fa en mangdforteckning tillbaka.

Tjansten ar ett skal runt samma motor som ``takeoff deliver`` kor. Den lagger
inte till nagon matning och den tar inte bort nagon flagga: spar, skala,
urvalsmetod och maskad zon foljer med i svaret precis som i Excel-filen.

Filsystemet ar flyktigt i drift. Projektprofilerna som versioneras i repot
foljer darfor med i avbilden, och en ny kalibrering lever bara sa lange
instansen gor det - den maste committas for att overleva en omstart.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from . import layergrammar as lg
from . import overlay as ov
from . import pipeline
from . import quantify as qt

app = FastAPI(title="Mangdforteckning VVS", docs_url="/api")

WORK = Path(tempfile.gettempdir()) / "takeoff-web"
WORK.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 40 * 1024 * 1024


@app.get("/health")
def health() -> dict:
    """Halsokontroll, och vilka projekt instansen ar kalibrerad for."""
    projects = sorted(p.stem for p in Path(lg.PROJECT_DIR).glob("*.json")) if os.path.isdir(lg.PROJECT_DIR) else []
    return {"status": "ok", "kalibrerade_projekt": projects}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _page(
        """
        <form class="drop" method="post" action="/mata" enctype="multipart/form-data">
          <label class="field">
            <span class="eyebrow">Ritning</span>
            <input type="file" name="fil" accept="application/pdf" required>
          </label>
          <button type="submit">Mät ritningen</button>
          <p class="note">Vektor-PDF. Motorn läser lager, verifierar skalan geometriskt
          och vägrar mäta hellre än att gissa den.</p>
        </form>
        """,
        title="Mängdförteckning ur ritning",
        lede="Ladda upp en VVS-ritning. Du får rörlängd per system, antal vertikala rör "
             "och känslighetstal — med varje osäkerhet utskriven.",
    )


@app.post("/mata", response_class=HTMLResponse)
async def mata(fil: UploadFile = File(...)) -> str:
    if not (fil.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Ladda upp en PDF.")
    job = WORK / uuid.uuid4().hex
    job.mkdir(parents=True, exist_ok=True)
    src = job / "ritning.pdf"
    size = 0
    with src.open("wb") as fh:
        while chunk := await fil.read(1 << 20):
            size += len(chunk)
            if size > MAX_BYTES:
                shutil.rmtree(job, ignore_errors=True)
                raise HTTPException(413, "Filen är större än 40 MB.")
            fh.write(chunk)

    name = Path(fil.filename).stem
    try:
        result = pipeline.run(str(src), drawing=name)
    except RuntimeError as exc:
        # R4: en ogiltig skala stoppar korningen. Det ar ratt beteende och ska
        # sagas rakt ut, inte doljas bakom ett servern-fel.
        return _page(
            f"""<div class="stop">
                  <h2>Motorn vägrade mäta</h2>
                  <p>{_esc(str(exc))}</p>
                  <p class="note">En gissad skala multiplicerar hela mängdförteckningen med
                  fel tal. Ritningen behöver en kalibrerad projektprofil, eller ett modulnät
                  som riktig text.</p>
                  <a class="back" href="/">Tillbaka</a>
                </div>""",
            title="Kunde inte mäta",
            lede=name,
        )

    qt.export_excel(result, str(job / f"mangd_{name}.xlsx"))
    ov.render(result, str(job / f"overlay_{name}.pdf"))

    rows = "".join(
        f"<tr><td class='mono'>{_esc(r.label)}</td><td class='mono'>{_esc(r.system or '')}</td>"
        f"<td class='num'>{r.length_m:.1f}</td><td class='num'>{r.verticals}</td>"
        f"<td class='tag'>{_esc(r.kind)}</td></tr>"
        for r in qt.build_rows(result)
    )
    s = qt.sensitivity(result)
    flags = result.flags + result.selection.flags + result.scale.flags
    flag_html = (
        "<ul class='flags'>" + "".join(f"<li class='mono'>{_esc(f)}</li>" for f in flags) + "</ul>"
        if flags else "<p class='note'>Inga flaggor.</p>"
    )
    return _page(
        f"""
        <div class="facts">
          <div><span class="eyebrow">Spår</span><b>{_esc(result.triage.track)}</b></div>
          <div><span class="eyebrow">Skala</span><b>1:{result.scale.value:.0f}</b>
               <em>{'verifierad' if result.scale.verified else 'OVERIFIERAD'}</em></div>
          <div><span class="eyebrow">Täckning</span><b>{result.coverage:.4f}</b></div>
          <div><span class="eyebrow">Urvalsmetod</span><b>{_esc(s['urvalsmetod'])}</b></div>
        </div>

        <table>
          <thead><tr><th>Beteckning</th><th>System</th><th class="num">Längd (m)</th>
                     <th class="num">Vertikala</th><th>Typ</th></tr></thead>
          <tbody>{rows}</tbody>
          <tfoot><tr><td colspan="2">Totalt i mängden</td>
                     <td class="num">{result.total_length_m:.1f}</td>
                     <td class="num">{len(result.net.verticals)}</td><td></td></tr></tfoot>
        </table>

        <p class="note">Dimensionen är inte ifylld. Lagret ger systemet men inte dimensionen,
        och den fylls inte i på gissning.</p>

        <div class="downloads">
          <a href="/hamta/{job.name}/mangd_{_esc(name)}.xlsx">Mängdförteckning (Excel)</a>
          <a href="/hamta/{job.name}/overlay_{_esc(name)}.pdf">Verifieringsoverlay (PDF)</a>
        </div>

        <h3>Flaggor och förutsättningar</h3>
        {flag_html}
        <a class="back" href="/">Mät en till</a>
        """,
        title=name,
        lede=f"{result.total_length_m:.1f} m i mängden"
             + (f", {result.masked_length_m:.1f} m i maskad zon som redovisas men inte räknas"
                if result.masked_length_m else ""),
    )


@app.get("/hamta/{job}/{filename}")
def hamta(job: str, filename: str):
    if not job.isalnum() or "/" in filename or ".." in filename:
        raise HTTPException(400, "Ogiltig sökväg.")
    path = WORK / job / filename
    if not path.is_file():
        raise HTTPException(404, "Filen finns inte kvar. Mät ritningen igen.")
    return FileResponse(path, filename=filename)


def _esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )


def _page(body: str, title: str, lede: str = "") -> str:
    return f"""<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{{--ground:#F4F6F8;--surface:#fff;--surface-2:#EDF1F5;--ink:#12171D;--ink-2:#3D4854;
--muted:#5A6673;--rule:#DCE2E9;--accent:#C4302B;--accent-soft:#F3DEDC;--ok:#1A7F4F}}
@media(prefers-color-scheme:dark){{:root{{--ground:#0D1116;--surface:#151A20;--surface-2:#1B222A;
--ink:#E6EBF0;--ink-2:#C2CCD6;--muted:#8E9BA8;--rule:#242C35;--accent:#F2635E;
--accent-soft:#3A2220;--ok:#3FBE81}}}}
*{{box-sizing:border-box}}
body{{background:var(--ground);color:var(--ink);margin:0;font-size:16px;line-height:1.6;
font-family:"IBM Plex Sans",system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:860px;margin:0 auto;padding:56px 24px 80px}}
h1{{font-family:Archivo,sans-serif;font-weight:700;letter-spacing:-.02em;
font-size:clamp(1.7rem,4vw,2.4rem);line-height:1.1;margin:0;text-wrap:balance}}
h2,h3{{font-family:Archivo,sans-serif;font-weight:600;margin:0}}
h3{{font-size:1rem;margin-top:8px}}
p{{margin:0}}
.lede{{color:var(--ink-2);margin-top:14px;font-size:1.05rem}}
header{{border-bottom:1px solid var(--rule);padding-bottom:28px;margin-bottom:32px}}
main{{display:flex;flex-direction:column;gap:24px}}
.eyebrow{{font-family:"IBM Plex Mono",monospace;font-size:.68rem;letter-spacing:.12em;
text-transform:uppercase;color:var(--muted);display:block}}
.mono{{font-family:"IBM Plex Mono",monospace;font-size:.86rem}}
.note{{color:var(--muted);font-size:.9rem}}
.drop{{background:var(--surface);border:1px solid var(--rule);border-radius:8px;
padding:28px;display:flex;flex-direction:column;gap:16px}}
.field{{display:flex;flex-direction:column;gap:8px}}
input[type=file]{{font:inherit;font-size:.92rem;color:var(--ink-2)}}
button,.downloads a,.back{{font:inherit;font-weight:600;font-size:.94rem;cursor:pointer;
border-radius:6px;padding:11px 20px;border:1px solid transparent;text-decoration:none;
display:inline-block;text-align:center}}
button{{background:var(--accent);color:#fff;width:fit-content}}
button:hover{{filter:brightness(1.07)}}
:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;
background:var(--rule);border:1px solid var(--rule);border-radius:8px;overflow:hidden}}
.facts>div{{background:var(--surface);padding:14px 16px;display:flex;flex-direction:column;gap:3px}}
.facts b{{font-family:"IBM Plex Mono",monospace;font-size:1.02rem;font-weight:500}}
.facts em{{font-style:normal;font-size:.76rem;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;background:var(--surface);
border:1px solid var(--rule);border-radius:8px;overflow:hidden;font-size:.92rem}}
th,td{{padding:10px 14px;text-align:left;border-top:1px solid var(--rule)}}
thead th{{background:var(--surface-2);border-top:none;font-weight:600;font-size:.8rem}}
.num{{text-align:right;font-variant-numeric:tabular-nums;font-family:"IBM Plex Mono",monospace}}
.tag{{font-size:.78rem;color:var(--ok)}}
tfoot td{{font-weight:600;background:var(--surface-2)}}
.downloads{{display:flex;gap:12px;flex-wrap:wrap}}
.downloads a{{background:var(--surface);border-color:var(--rule);color:var(--ink)}}
.downloads a:hover{{border-color:var(--accent);color:var(--accent)}}
.back{{background:none;color:var(--accent);padding-left:0}}
.flags{{margin:0;padding-left:1.1rem;display:flex;flex-direction:column;gap:5px;color:var(--ink-2)}}
.stop{{background:var(--surface);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;
padding:22px;display:flex;flex-direction:column;gap:12px}}
</style></head><body><div class="wrap">
<header><h1>{_esc(title)}</h1>{f'<p class="lede">{_esc(lede)}</p>' if lede else ''}</header>
<main>{body}</main></div></body></html>"""
