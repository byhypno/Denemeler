"""Güvenli şema güncellemesi: bekleyen veritabanı geçişi varsa ÖNCE yedek alır, doğrular, sonra uygular."""
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from . import yedek as yd


def bekleyen_gecisler():
    yurutucu = MigrationExecutor(connections["default"])
    return yurutucu.migration_plan(yurutucu.loader.graph.leaf_nodes())


def veritabani_dolu_mu() -> bool:
    """Dosya var ve içinde tablo var mı? (Yeni kurulumda yedeğe gerek yok.)"""
    yol = Path(settings.DATABASES["default"]["NAME"])
    if not yol.exists() or yol.stat().st_size == 0:
        return False
    con = sqlite3.connect(yd.salt_okunur_uri(yol), uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] > 0
    finally:
        con.close()


def guvenli_migrate(yaz=print) -> dict:
    """Dönüş: {'uygulanan': n, 'yedek': Path|None}. Yedek doğrulanamazsa geçiş UYGULANMAZ."""
    plan = bekleyen_gecisler()
    if not plan:
        return {"uygulanan": 0, "yedek": None}
    yedek = None
    if veritabani_dolu_mu():
        hedef = (settings.YEDEK_DIZINLERI or [Path(settings.VERI_DIZINI) / "otomatik_yedek"])[0]
        yaz(f"{len(plan)} veritabanı güncellemesi bekliyor. Önce yedek alınıyor: {hedef}")
        yedek = yd.yedek_olustur(hedef)
        d = yd.yedek_dogrula(yedek)
        if not d.ok:
            raise yd.YedekHatasi("Güncelleme öncesi yedek doğrulanamadı; veritabanı DEĞİŞTİRİLMEDİ: " + "; ".join(d.hatalar))
        yaz(f"Yedek hazır ve doğrulandı: {yedek.name}")
    call_command("migrate", interactive=False, verbosity=0)
    yaz(f"{len(plan)} güncelleme uygulandı.")
    return {"uygulanan": len(plan), "yedek": yedek}
