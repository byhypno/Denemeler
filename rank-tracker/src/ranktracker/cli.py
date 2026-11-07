from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from . import db
from .config import load_config
from .dashboard import write_dashboard
from .providers import make_provider, target_day
from .report import change_rows, render_text


def cmd_fetch(args, cfg) -> int:
    provider = make_provider(cfg)
    conn = db.connect(cfg.database)
    end = target_day(cfg)
    total = 0
    for offset in range(args.backfill, -1, -1):  # eski -> yeni
        day = end - timedelta(days=offset)
        for site in cfg.sites:
            total += db.save(conn, provider.fetch(site, day))
    print(f"{total} kayit islendi (son gun: {end}).")
    return 0


def cmd_report(args, cfg) -> int:
    conn = db.connect(cfg.database)
    print(render_text(change_rows(conn, cfg)))
    return 0


def cmd_dashboard(args, cfg) -> int:
    conn = db.connect(cfg.database)
    print(f"Yazildi: {write_dashboard(conn, cfg, args.out, args.days)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rank", description="Gunluk Google siralama takibi")
    p.add_argument("-c", "--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="Siralari cek ve veritabanina kaydet")
    f.add_argument("--backfill", type=int, default=0, help="Ek olarak kac gun geriye git")
    f.set_defaults(fn=cmd_fetch)
    r = sub.add_parser("report", help="Terminalde rapor")
    r.set_defaults(fn=cmd_report)
    d = sub.add_parser("dashboard", help="HTML pano uret")
    d.add_argument("--out", default="site")
    d.add_argument("--days", type=int, default=30)
    d.set_defaults(fn=cmd_dashboard)
    args = p.parse_args(argv)
    try:
        return args.fn(args, load_config(args.config))
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
