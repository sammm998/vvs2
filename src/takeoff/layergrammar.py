"""R2 - lagergrammatiken harleds ur ritningen och ateranvands inom projektet.

Pa spar A bar varje bana sitt lagernamn, och lagernamnet ar satt av en
CAD-standard som skiljer installationens ledningar fran dess text, symboler
och fran byggnadsunderlaget. Vilket falt som gor det - och vilket varde
faltet har - varierar mellan projekterande foretag, sa det far aldrig
hardkodas (R1, R2).

Det harleds i stallet ur EN kalibrerad ritning: den vars mangder ar handmatta.
Ur facitets geometri vet vi vilka stilkluster som faktiskt mattes; ur deras
lagernamn induceras den kortaste teckenfoljd som alla rorlager delar och som
inget annat lager i ritningen bar.

Regeln sparas i projektprofilen och far anvandas pa ovriga ritningar i SAMMA
projekt - aldrig i ett annat. Det ar precis den arbetsgang CLAUDE.md avslutar
med: en handmatt ritning per nytt projekt kalibrerar hela profilen.
"""

from __future__ import annotations

import collections
import json
import os
import re
from dataclasses import dataclass, field


@dataclass
class LayerRule:
    """Inducerad regel for vilka lager som bar matbar ledningsgeometri."""

    tokens: list[str] = field(default_factory=list)
    valid: bool = True
    reason: str = ""
    project_key: str | None = None
    calibrated_on: str | None = None
    positives: list[str] = field(default_factory=list)
    negatives_excluded: int = 0

    def matches(self, layer: str | None) -> bool:
        if not layer or not self.tokens:
            return False
        marked = "|" + layer + "|"
        return any(t in marked for t in self.tokens)

    def applies_to(self, project_key: str | None) -> bool:
        """Profilen far ateranvandas inom samma projekt, aldrig mellan projekt."""
        return (
            bool(self.tokens)
            and self.valid
            and project_key is not None
            and project_key == self.project_key
        )

    def as_dict(self) -> dict:
        return {
            "tokens": self.tokens,
            "valid": self.valid,
            "reason": self.reason,
            "project_key": self.project_key,
            "calibrated_on": self.calibrated_on,
            "positives": self.positives,
            "negatives_excluded": self.negatives_excluded,
        }

    @staticmethod
    def from_dict(d: dict | None) -> "LayerRule":
        if not d:
            return LayerRule()
        return LayerRule(
            tokens=list(d.get("tokens") or []),
            valid=bool(d.get("valid", True)),
            reason=str(d.get("reason") or ""),
            project_key=d.get("project_key"),
            calibrated_on=d.get("calibrated_on"),
            positives=list(d.get("positives") or []),
            negatives_excluded=int(d.get("negatives_excluded") or 0),
        )


def project_key(layers: list[str]) -> str | None:
    """Projektets identitet, harledd ur lagernamnen.

    CAD-lager fran en extern referens bar modellens beteckning som prefix,
    och modellbeteckningen inleds med PROJEKTNUMRET:

        268140-W-50-P-A-00|V-53BB-FE--S3-     VVS-modellen
        268140-A-40-P-A-01|A-------EXN        arkitektmodellen

    En och samma ritning kan bara pa flera modeller samtidigt, och samma
    projekt anvander flera modellfiler. Nyckeln ar darfor projektnumret -
    det forsta faltet i det prefix som bar flest lager - inte hela
    modellbeteckningen. Att anvanda modellbeteckningen skulle gora varje
    modellfil till ett eget "projekt" och tvinga fram en ny kalibrering for
    ritningar som foljer exakt samma konvention.

    R2 galler oforandrat: profilen far ateranvandas inom samma projekt,
    aldrig mellan projekt.
    """
    per_prefix: collections.Counter = collections.Counter()
    for layer in layers:
        if "|" in layer:
            per_prefix[layer.split("|", 1)[0]] += 1
    if not per_prefix:
        return None
    dominant, n = per_prefix.most_common(1)[0]
    if n < 2:
        return None
    lead = dominant.split("-", 1)[0].strip()
    return lead or dominant


def induce(positives: list[str], negatives: list[str], max_fields: int = 3) -> list[str]:
    """Inducera de lagerfalt som skiljer ledningslagren fran allt annat.

    Kandidaterna ar inte godtyckliga teckenfoljder utan *avgransade falt*:
    delstrangar som borjar direkt efter och slutar direkt fore en avgransare
    ('-' eller '|'). En godtycklig teckenfoljd som "B-F" kan rada over den
    kalibrerade ritningen av en slump; ett helt falt som "-FE-" ar ett varde
    i CAD-standarden och overlever till nasta ritning.

    Bland de kandidater som taxker lika manga positiva valjs den mest
    specifika, det vill saga den langsta - inte den kortaste.
    """
    pos = [p for p in positives if p]
    neg = [n for n in negatives if n]
    if not pos:
        return []

    def field_candidates(name: str) -> set[str]:
        """Avgransade falt och korta faltfoljder ur ett lagernamn."""
        marked = "|" + name + "|"
        breaks = [i for i, ch in enumerate(marked) if ch in "-|"]
        out: set[str] = set()
        for bi, start in enumerate(breaks):
            for end in breaks[bi + 1 : bi + 1 + max_fields]:
                tok = marked[start : end + 1]
                inner = tok.strip("-|")
                if inner and len(tok) <= 16:
                    out.add(tok)
        return out

    def n_fields(tok: str) -> int:
        return len([f for f in tok.strip("-|").split("-") if f != ""]) or 1

    def negatives_matched(tok: str) -> int:
        return sum(1 for n in neg if tok in ("|" + n + "|"))

    # Steg 1: racker ETT falt for alla positiva? Ett enskilt faltvarde ar ett
    # varde i CAD-standarden; en lang faltfoljd ar ritningens egen slump.
    # Nagot enstaka omatchat lager far traffas - ett ledningslager som facit
    # inte rakade tacka ar inte ett motbevis, och att kräva noll traffar
    # skulle lata just det lagret forgifta induktionen.
    all_cands: set[str] = set()
    for p_ in pos:
        all_cands |= field_candidates(p_)
    full = [t for t in all_cands if all(t in ("|" + p_ + "|") for p_ in pos)]
    if full:
        best_tok = min(full, key=lambda t: (negatives_matched(t), n_fields(t), len(t)))
        return [best_tok]

    # Steg 2: inget enskilt falt racker - dela upp de positiva och inducera
    # ett falt per delmangd.
    def clean(tok: str) -> bool:
        return negatives_matched(tok) == 0

    remaining = list(pos)
    tokens: list[str] = []
    guard = 0
    while remaining and guard < 20:
        guard += 1
        best = None
        for tok in field_candidates(remaining[0]):
            if not clean(tok):
                continue
            covered = sum(1 for p_ in remaining if tok in ("|" + p_ + "|"))
            if not covered:
                continue
            score = (covered, -n_fields(tok), -len(tok))
            if best is None or score > best[0]:
                best = (score, tok)
        if best is None:
            break
        tok = best[1]
        tokens.append(tok)
        remaining = [p_ for p_ in remaining if tok not in ("|" + p_ + "|")]
    return tokens

def calibrate(result, geometry: list[dict], tol_units: float = 2.0) -> LayerRule:
    """Harled regeln ur en ritning vars facitgeometri ar kand.

    De positiva lagren ar de som facitets polylinjer faktiskt loper pa. De
    negativa ar alla ovriga lager som bar geometri i planytan.
    """
    from .evaluate import facit_scope

    # De negativa filtren (text, schraffering, ram, vagg) ar oberoende av de
    # grindar som avgor rorurvalet, sa de far anvandas har utan cirkularitet.
    # Ett textkluster kan aldrig vara ett ledningslager, hur nara facitlinjen
    # det an rakar ligga.
    disqualified = {"text_or_glyph", "hatch", "frame", "degenerate"}
    all_clusters = [
        c.id
        for c in result.styles.clusters
        if c.total_length > 0
        and result.zones.classify(c.bbox) == "plan"
        and result.selection.reasons.get(c.id) not in disqualified
    ]
    scope = facit_scope(result, geometry, tol_units, clusters=all_clusters)
    # facit_by_layer bygger pa result.quantities; vid kalibrering vill vi ha
    # kopplingen kluster -> facitlangd direkt.
    labels = scope.get("__labels_by_cluster__") or {}
    positives = sorted(
        {
            result.styles.get(cid).key.layer
            for cid in labels
            if result.styles.get(cid).key.layer
        }
    )

    in_plan_layers = {
        p.layer
        for p in result.sheet.paths
        if p.layer and p.length > 0 and result.zones.classify(p.bbox) == "plan"
    }
    negatives = sorted(in_plan_layers - set(positives))

    tokens = induce(positives, negatives)

    # Validering: en regel som traffar ett lager som de negativa filtren
    # redan domt som text, schraffering eller ram ar for bred. Da har
    # kalibreringen misslyckats, och det ska sagas rakt ut i stallet for att
    # en dalig regel levereras och tyst forstor nasta ritning.
    disqualified = {
        result.styles.get(c.id).key.layer
        for c in result.styles.clusters
        if result.selection.reasons.get(c.id) in {"text_or_glyph", "hatch", "frame"}
        and result.styles.get(c.id).key.layer
    } - set(positives)

    rule = LayerRule(
        tokens=tokens,
        project_key=project_key(sorted(in_plan_layers)),
        calibrated_on=result.drawing,
        positives=positives,
        negatives_excluded=len(negatives),
    )
    if not tokens:
        rule.valid = False
        rule.reason = "ingen lagerregel kunde induceras ur facitgeometrin"
    else:
        leaked = sorted(l for l in disqualified if rule.matches(l))
        if leaked:
            rule.valid = False
            rule.reason = (
                "regeln traffar lager som ar text/schraffering/ram: "
                + ", ".join(l.split("|")[-1] for l in leaked[:5])
                + " - kalibrera pa en ritning med tatare facit"
            )
    return rule


# --------------------------------------------------------------------------
# Lagring. Regeln hor till PROJEKTET, inte till den enskilda ritningen.

PROJECT_DIR = "profiles/_projects"


def _slug(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)


def save_project(rule: LayerRule, scale_reference=None, directory: str = PROJECT_DIR) -> str | None:
    """Spara projektets profil: lagerregel och skalreferens i samma fil."""
    if not rule.project_key or not rule.valid:
        return None
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{_slug(rule.project_key)}.json")
    payload = {
        "project_key": rule.project_key,
        "layer_rule": rule.as_dict(),
        "scale_reference": scale_reference.as_dict() if scale_reference else None,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return path


def _load_payload(key: str | None, directory: str = PROJECT_DIR) -> dict | None:
    if not key:
        return None
    path = os.path.join(directory, f"{_slug(key)}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_project_rule(key: str | None, directory: str = PROJECT_DIR) -> LayerRule | None:
    payload = _load_payload(key, directory)
    if not payload:
        return None
    return LayerRule.from_dict(payload.get("layer_rule"))


def load_project_scale(key: str | None, directory: str = PROJECT_DIR):
    from .scale import ScaleReference

    payload = _load_payload(key, directory)
    if not payload:
        return None
    return ScaleReference.from_dict(payload.get("scale_reference"))
