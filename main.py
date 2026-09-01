"""Startpunkt for drift.

Porten last av Python sjalv i stallet for att expanderas i startkommandot.
En ${PORT:-8000} som inte gar genom ett skal skickas vidare ordagrant till
uvicorn, som da binder fel port - och da svarar tjansten aldrig, vilket ser ut
som en tom vit sida i webblasaren i stallet for ett fel.

Sokvagen till src laggs till innan importen sa att tjansten startar aven nar
byggaren installerat beroendena men inte sjalva paketet.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def _port() -> int:
    raw = (os.environ.get("PORT") or "").strip()
    try:
        return int(raw)
    except ValueError:
        print(f"[takeoff] PORT={raw!r} gick inte att tolka, anvander 8000", flush=True)
        return 8000


def main() -> None:
    port = _port()
    print(f"[takeoff] startar pa 0.0.0.0:{port}", flush=True)
    try:
        from takeoff.web import app
    except Exception as exc:  # pragma: no cover - ska synas i driftloggen
        print(f"[takeoff] KUNDE INTE IMPORTERA APPEN: {type(exc).__name__}: {exc}", flush=True)
        raise
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
