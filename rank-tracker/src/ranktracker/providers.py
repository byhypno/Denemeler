from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Protocol

from .config import Config, Site
from .db import Observation


class Provider(Protocol):
    def fetch(self, site: Site, day: date) -> list[Observation]: ...


class MockProvider:
    """Deneme/test icin deterministik sahte veri (ag erisimi gerektirmez)."""

    def fetch(self, site: Site, day: date) -> list[Observation]:
        out = []
        for kw in site.keywords:
            h = int(hashlib.sha256(f"{site.name}|{kw}".encode()).hexdigest(), 16)
            base = 3 + h % 40
            wobble = (int(hashlib.sha256(f"{kw}|{day}".encode()).hexdigest(), 16) % 7) / 2 - 1.5
            pos = max(1.0, round(base + wobble, 1))
            out.append(Observation(site.name, kw, day.isoformat(), pos, clicks=int(100 / pos), impressions=int(2000 / pos)))
        return out


class GSCProvider:
    """Google Search Console Search Analytics API (resmi, ucretsiz).

    Not: donen deger, o gun icin ORTALAMA pozisyondur; anlik tam sira degildir.
    """

    SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

    def __init__(self, credentials_file: str):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Gerekli paketler yok: pip install 'rank-tracker[gsc]'") from e
        creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=[self.SCOPE])
        self._service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    def fetch(self, site: Site, day: date) -> list[Observation]:
        body = {
            "startDate": day.isoformat(),
            "endDate": day.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 25000,
        }
        resp = self._service.searchanalytics().query(siteUrl=site.property, body=body).execute()
        return parse_gsc_rows(site, day, resp.get("rows", []))


def parse_gsc_rows(site: Site, day: date, rows: list[dict]) -> list[Observation]:
    """Yalnizca takip edilen anahtar kelimeleri alir; verisi olmayanlar position=None olur."""
    wanted = {k.casefold(): k for k in site.keywords}
    found: dict[str, Observation] = {}
    for r in rows:
        key = r["keys"][0].casefold()
        if key in wanted:
            kw = wanted[key]
            found[kw] = Observation(
                site.name, kw, day.isoformat(), round(r["position"], 2), int(r.get("clicks", 0)), int(r.get("impressions", 0))
            )
    return [found.get(k) or Observation(site.name, k, day.isoformat(), None) for k in site.keywords]


def make_provider(cfg: Config) -> Provider:
    if cfg.provider == "mock":
        return MockProvider()
    if cfg.provider == "gsc":
        if not cfg.credentials_file:
            raise RuntimeError("credentials_file veya GSC_CREDENTIALS_FILE ayarlanmali")
        return GSCProvider(cfg.credentials_file)
    raise ValueError(f"Bilinmeyen provider: {cfg.provider}")


def target_day(cfg: Config, today: date | None = None) -> date:
    return (today or date.today()) - timedelta(days=cfg.gsc_lag_days if cfg.provider == "gsc" else 0)
