"""Sokvagar som halller aven i drift.

Profilerna versioneras i repot och maste hittas oavsett vilken katalog
processen startas fran. En relativ sokvag racker vid utveckling men tappar
projektprofilen sa fort tjansten kors fran en annan arbetskatalog - och da
faller ritningen tillbaka pa okalibrerat lage utan att nagon marker det.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Katalogen som innehaller ``src/`` och ``profiles/``.
ROOT = Path(__file__).resolve().parents[2]


def resolve(relative: str, env: str | None = None) -> str:
    """Absolut sokvag till en katalog i projektet.

    En miljovariabel far peka om den i drift, dar filsystemet kan se ut hur
    som helst. Annars anvands katalogen bredvid koden, och som sista utvag
    arbetskatalogen.
    """
    if env:
        override = os.environ.get(env)
        if override:
            return str(Path(override).expanduser())
    anchored = ROOT / relative
    if anchored.exists():
        return str(anchored)
    local = Path.cwd() / relative
    if local.exists():
        return str(local)
    return str(anchored)
