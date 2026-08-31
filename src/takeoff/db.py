"""SQLite-lagring for korningar, sparrade banor, facit och utvarderingar."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone

DEFAULT_PATH = "out/takeoff.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drawing TEXT NOT NULL,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    git_sha TEXT,
    track TEXT,
    scale_value REAL,
    scale_verified INTEGER,
    profile_json TEXT
);
CREATE TABLE IF NOT EXISTS strands (
    run_id INTEGER, strand_id INTEGER, cluster_id TEXT,
    length_pt REAL, length_m REAL, label TEXT, label_source TEXT,
    points_json TEXT
);
CREATE TABLE IF NOT EXISTS blocked_paths (
    run_id INTEGER, path_id INTEGER, cluster_id TEXT, reason TEXT, step TEXT
);
CREATE TABLE IF NOT EXISTS quantities (
    run_id INTEGER, label TEXT, system TEXT, dimension TEXT,
    length_m REAL, verticals REAL, bends INTEGER, tees INTEGER,
    status TEXT, flags TEXT
);
CREATE TABLE IF NOT EXISTS ground_truth (
    drawing TEXT, label TEXT, system TEXT, material TEXT, dimension TEXT,
    length_m REAL, vertical_count REAL, layer TEXT, is_vertical INTEGER
);
CREATE TABLE IF NOT EXISTS eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER, drawing TEXT, created_at TEXT, git_sha TEXT,
    metrics_json TEXT
);
"""


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "unknown"


def connect(path: str = DEFAULT_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def replace_ground_truth(con: sqlite3.Connection, gt) -> int:
    """Omimport raderar tidigare facit for samma ritning."""
    con.execute("DELETE FROM ground_truth WHERE drawing = ?", (gt.drawing,))
    con.executemany(
        "INSERT INTO ground_truth VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                r.drawing,
                r.label,
                r.system,
                r.material,
                r.dimension,
                r.length_m,
                r.vertical_count,
                r.layer,
                int(r.is_vertical),
            )
            for r in gt.rows
        ],
    )
    con.commit()
    return len(gt.rows)


def save_eval(con: sqlite3.Connection, run_id: int | None, drawing: str, metrics: dict) -> int:
    cur = con.execute(
        "INSERT INTO eval_results (run_id, drawing, created_at, git_sha, metrics_json) VALUES (?,?,?,?,?)",
        (run_id, drawing, now(), git_sha(), json.dumps(metrics, ensure_ascii=False)),
    )
    con.commit()
    return cur.lastrowid
