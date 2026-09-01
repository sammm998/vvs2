"""Startpunkt for drift.

Byggare som Railpack letar efter main.py i rotkatalogen. Sjalva tjansten
ligger i takeoff.web; den har filen finns for att gora den korbar utan
konfiguration, aven nar paketet inte ar installerat i miljon.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import uvicorn  # noqa: E402

from takeoff.web import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
