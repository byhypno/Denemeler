from __future__ import annotations

import html
import sqlite3
from pathlib import Path

from .config import Config
from .db import history
from .report import arrow, change_rows

W, H, PAD = 360, 90, 8


def sparkline(points: list[tuple[str, float | None]]) -> str:
    """Satir ici SVG grafik. Y ekseni ters: 1. sira en ustte."""
    vals = [(i, p) for i, (_, p) in enumerate(points) if p is not None]
    if len(vals) < 2:
        return '<span class="muted">yeterli veri yok</span>'
    lo, hi = min(p for _, p in vals), max(p for _, p in vals)
    span = (hi - lo) or 1.0
    n = max(len(points) - 1, 1)
    xy = [(PAD + i / n * (W - 2 * PAD), PAD + (p - lo) / span * (H - 2 * PAD)) for i, p in vals]
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    lx, ly = xy[-1]
    return (
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="sira gecmisi">'
        f'<polyline fill="none" stroke="var(--line)" stroke-width="2" points="{d}"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="var(--line)"/></svg>'
    )


def build_html(conn: sqlite3.Connection, cfg: Config, days: int = 30) -> str:
    changes = {(s, k): (d, p, dl) for s, k, d, p, dl in change_rows(conn, cfg)}
    sections = []
    for site in cfg.sites:
        rows = []
        for kw in site.keywords:
            day, pos, delta = changes[(site.name, kw)]
            cls = "up" if delta and delta < 0 else "down" if delta and delta > 0 else ""
            rows.append(
                f"<tr><td>{html.escape(kw)}</td><td class='num'>{'-' if pos is None else f'{pos:g}'}</td>"
                f"<td class='{cls}'>{html.escape(arrow(delta))}</td>"
                f"<td>{sparkline(history(conn, site.name, kw, days))}</td></tr>"
            )
        sections.append(
            f"<section><h2>{html.escape(site.name)} <small>{html.escape(site.property)}</small></h2>"
            "<table><thead><tr><th>Anahtar kelime</th><th>Sira</th><th>Degisim</th><th>Son "
            f"{days} gun</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
        )
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sira Takibi</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#6b6b6b;--card:#f6f6f7;--line:#2563eb;--up:#15803d;--down:#b91c1c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121212;--fg:#eee;--muted:#9a9a9a;--card:#1d1d20;--line:#6ea8ff;--up:#4ade80;--down:#f87171}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:960px;margin:0 auto}}section{{background:var(--card);border-radius:12px;padding:16px;margin:16px 0;overflow-x:auto}}
h2{{margin:0 0 8px}}small,.muted{{color:var(--muted);font-weight:400}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid rgba(128,128,128,.25)}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
td svg{{width:200px;height:50px}}.up{{color:var(--up)}}.down{{color:var(--down)}}
</style></head><body><main><h1>Google Sira Takibi</h1>
<p class="muted">Search Console verisi: sira, o gunun ortalama pozisyonudur (dusuk sayi = daha iyi).</p>
{''.join(sections)}</main></body></html>"""


def write_dashboard(conn: sqlite3.Connection, cfg: Config, out_dir: str, days: int = 30) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(build_html(conn, cfg, days), encoding="utf-8")
    return path
