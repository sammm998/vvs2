"""R3 - triage fore matning.

Varje ritning klassas innan nagot mats:

    A   Vektor + OCG-lager      Mangder per system som MATVARDEN
    B   Vektor utan lager       Totalsumma som matvarde, per system som UPPSKATTNING
    C   Raster                  Allt flaggat osakert, annan metod

Ett spar B-resultat presenterat som spar A ar ett allvarligare fel an ett
saknat ror. Sparet foljer med varje leverans.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .extract import Sheet


@dataclass
class TriageResult:
    track: str
    has_ocgs: bool
    layers: list[str]
    real_text_in_plan: int
    text_is_vectorised: bool
    n_paths: int
    notes: list[str] = field(default_factory=list)

    @property
    def per_system_is_measurement(self) -> bool:
        """Far per-system-siffror levereras som matvarden?"""
        return self.track == "A"

    def as_dict(self) -> dict:
        return {
            "track": self.track,
            "has_ocgs": self.has_ocgs,
            "layers": self.layers,
            "n_paths": self.n_paths,
            "real_text_in_plan": self.real_text_in_plan,
            "text_is_vectorised": self.text_is_vectorised,
            "per_system_delivery": "matvarde" if self.per_system_is_measurement else "uppskattning",
            "notes": self.notes,
        }


def triage(sheet: Sheet, plan=None) -> TriageResult:
    notes: list[str] = []
    n_paths = len(sheet.paths)

    if n_paths == 0:
        return TriageResult("C", False, [], 0, True, 0, ["inga vektorbanor - rasterritning"])

    has_ocgs = sheet.has_ocgs
    layers = sheet.layers
    track = "A" if has_ocgs else "B"
    if not has_ocgs:
        notes.append("inga OCG-lager: per-system-siffror far bara levereras som uppskattning")

    in_plan = 0
    for t in sheet.texts:
        if plan is None:
            in_plan += 1
        else:
            cx, cy = t.center
            if plan[0] <= cx <= plan[2] and plan[1] <= cy <= plan[3]:
                in_plan += 1
    vectorised = in_plan < 50
    if vectorised:
        notes.append(
            f"endast {in_plan} riktiga textord i planytan: ritningstexten ar "
            "vektoriserad (SHX) och kraver glyfklustring + vision"
        )
    return TriageResult(track, has_ocgs, layers, in_plan, vectorised, n_paths, notes)
