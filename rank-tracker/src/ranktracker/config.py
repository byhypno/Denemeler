from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Site:
    name: str
    property: str
    keywords: list[str] = field(default_factory=list)


@dataclass
class Config:
    database: str
    provider: str
    credentials_file: str | None
    gsc_lag_days: int
    sites: list[Site]


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    sites = []
    for s in raw.get("sites") or []:
        if not s.get("name") or not s.get("property"):
            raise ValueError("Her site icin 'name' ve 'property' gerekli")
        sites.append(Site(s["name"], s["property"], [str(k) for k in s.get("keywords") or []]))
    if not sites:
        raise ValueError("Yapilandirmada en az bir site olmali")
    return Config(
        database=raw.get("database", "data/ranks.db"),
        provider=raw.get("provider", "gsc"),
        credentials_file=raw.get("credentials_file") or os.environ.get("GSC_CREDENTIALS_FILE"),
        gsc_lag_days=int(raw.get("gsc_lag_days", 3)),
        sites=sites,
    )
