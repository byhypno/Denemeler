from __future__ import annotations

import sqlite3

from .config import Config
from .db import latest_two


def change_rows(conn: sqlite3.Connection, cfg: Config):
    """(site, kelime, gun, sira, degisim) satirlari. degisim<0 = yukseldi (sira sayisi kuculdu)."""
    rows = []
    for site in cfg.sites:
        for kw in site.keywords:
            new, old = latest_two(conn, site.name, kw)
            if new is None:
                rows.append((site.name, kw, None, None, None))
            else:
                delta = round(new[1] - old[1], 2) if old else None
                rows.append((site.name, kw, new[0], new[1], delta))
    return rows


def arrow(delta: float | None) -> str:
    if delta is None:
        return "-"
    if delta < 0:
        return f"+{abs(delta):g} (yukseldi)"
    if delta > 0:
        return f"-{delta:g} (dustu)"
    return "="


def render_text(rows) -> str:
    out = [f"{'SITE':<14}{'ANAHTAR KELIME':<32}{'GUN':<12}{'SIRA':>7}  DEGISIM"]
    for site, kw, day, pos, delta in rows:
        out.append(f"{site:<14}{kw[:30]:<32}{(day or '-'):<12}{(f'{pos:g}' if pos is not None else '-'):>7}  {arrow(delta)}")
    return "\n".join(out)
