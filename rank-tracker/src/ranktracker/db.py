from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ranks (
    site TEXT NOT NULL,
    keyword TEXT NOT NULL,
    day TEXT NOT NULL,            -- YYYY-MM-DD
    position REAL,                -- NULL: o gun veri yok
    clicks INTEGER NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (site, keyword, day)
);
"""


@dataclass
class Observation:
    site: str
    keyword: str
    day: str
    position: float | None
    clicks: int = 0
    impressions: int = 0


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save(conn: sqlite3.Connection, obs: list[Observation]) -> int:
    """Ayni (site, kelime, gun) tekrar gelirse uzerine yazar; boylece gunluk calisma tekrarlanabilir."""
    conn.executemany(
        "INSERT OR REPLACE INTO ranks (site, keyword, day, position, clicks, impressions)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(o.site, o.keyword, o.day, o.position, o.clicks, o.impressions) for o in obs],
    )
    conn.commit()
    return len(obs)


def history(conn: sqlite3.Connection, site: str, keyword: str, days: int = 30) -> list[tuple[str, float | None]]:
    rows = conn.execute(
        "SELECT day, position FROM ranks WHERE site=? AND keyword=? ORDER BY day DESC LIMIT ?",
        (site, keyword, days),
    ).fetchall()
    return list(reversed(rows))


def latest_two(conn: sqlite3.Connection, site: str, keyword: str):
    """En son iki olcum (yeni, onceki). Veri olmayan gunler (position NULL) atlanir."""
    rows = conn.execute(
        "SELECT day, position FROM ranks WHERE site=? AND keyword=? AND position IS NOT NULL"
        " ORDER BY day DESC LIMIT 2",
        (site, keyword),
    ).fetchall()
    return (rows[0] if rows else None, rows[1] if len(rows) > 1 else None)
