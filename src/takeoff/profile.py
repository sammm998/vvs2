"""R2 - projektprofilen harleds ur ritningen, aldrig ateranvands.

Profilen sparas som ``profiles/<ritning>.json`` och versioneras i git. Den far
ateranvandas inom samma projekt, aldrig mellan projekt: lagernamn, farger,
linjebredder och beteckningsgrammatik varierar mellan projekterande foretag.
"""

from __future__ import annotations

import json
import os
from typing import Any

PROFILE_DIR = "profiles"


def derive(result) -> dict[str, Any]:
    r = result
    widths = sorted(p.width for p in r.sheet.paths if p.width > 0)

    def pct(p: float) -> float:
        if not widths:
            return 0.0
        return round(widths[max(0, min(len(widths) - 1, int(len(widths) * p)))], 3)

    pipe_ids = set(r.selection.pipe_clusters)
    chain_any = next(iter(r.chains.values()), None)

    return {
        "drawing": r.drawing,
        "source": os.path.basename(r.source),
        "track": r.triage.track,
        "has_ocgs": r.triage.has_ocgs,
        "layers": r.triage.layers,
        "scale": r.scale.as_dict(),
        "width_percentiles": {
            "p10": pct(0.10),
            "p25": pct(0.25),
            "p50": pct(0.50),
            "p75": pct(0.75),
            "p90": pct(0.90),
        },
        "style_clusters": [
            {
                **c.as_dict(),
                "class": "pipe" if c.id in pipe_ids else r.selection.reasons.get(c.id, "unknown"),
                "confidence": round(r.selection.scores.get(c.id, 0.0), 3),
            }
            for c in r.styles.clusters
        ],
        "status_rule": _status_rule(r),
        "pipe_representation": _representation(r),
        # Vaggregeln ar ett PROJEKTBESLUT, inte en detekteringsfraga. Den satts
        # av manniska; motorn mater alltid overlappet ror-i-vaggzon och
        # redovisar det som kanslighetstal oavsett beslut.
        "wall_rule": "measure_through",
        "label_grammar": "SYSTEM-TYP[-DIM]",
        "chain_threshold": chain_any.as_dict() if chain_any else None,
        "zones": r.zones.as_dict(),
        "flags": r.flags + r.selection.flags + r.scale.flags,
    }


def _status_rule(r) -> dict:
    """R5 - vilket falt skiljer ny / befintlig / rivning?

    Alla fyra hypoteserna provas. Den som ger en ren uppdelning av
    rorgeometrin vinner. Hittas ingen redovisas det uttryckligen i stallet
    for att gissas.
    """
    from .status import detect_status_rule

    return detect_status_rule(r)


def _representation(r) -> str:
    """single_line eller double_line, avgjort ur rorklustrens egen geometri."""
    from .status import pipe_representation

    return pipe_representation(r)


def save(profile: dict, directory: str = PROFILE_DIR) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{profile['drawing']}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2, ensure_ascii=False)
    return path


def load(drawing: str, directory: str = PROFILE_DIR) -> dict | None:
    path = os.path.join(directory, f"{drawing}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
