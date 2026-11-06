"""Yedekleme, doğrulama ve geri yükleme.

Bir yedek, tek bir .zip dosyasıdır:
  cari.sqlite3    SQLite'ın kendi yedekleme API'siyle alınmış TUTARLI anlık görüntü (WAL açıkken bile güvenli)
  ekler/...       ek dosya deposu
  MANIFEST.json   her dosyanın SHA-256 özeti, boyutu ve kayıt sayıları

GİZLİ ANAHTAR (secret.key) YEDEĞE KONMAZ: yedek bir bulut klasörüne/USB'ye giderse anahtar sızmasın.
(Anahtar kaybolursa yalnızca açık oturumlar kapanır; veri etkilenmez.)
YEDEK ŞİFRELENMEZ: kullanıcı parolası özetleri ve tüm mali veri içerir. Şifreli bir sürücüye
(BitLocker/VeraCrypt) veya şifreli bulut klasörüne alın.
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils._os import safe_join

SURUM = 1
AD_DESENI = re.compile(r"^cari_yedek_(\d{8})_(\d{6})\.zip$")
SAYILAR = {"cari": "defter_cari", "belge": "defter_belge", "kasa_hareketi": "defter_kasahareketi",
           "ek": "defter_ek"}


class YedekHatasi(Exception):
    pass


def _sha256(yol) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1024 * 1024), b""):
            h.update(parca)
    return h.hexdigest()


def _db_yolu() -> Path:
    return Path(settings.DATABASES["default"]["NAME"])


def _sayilar(db_yolu) -> dict:
    sonuc = {}
    con = sqlite3.connect(f"file:{db_yolu}?mode=ro", uri=True)
    try:
        for ad, tablo in SAYILAR.items():
            try:
                sonuc[ad] = con.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0]
            except sqlite3.Error:
                sonuc[ad] = None
    finally:
        con.close()
    return sonuc


def _butunluk(db_yolu) -> str:
    """'ok' ya da sorunun metni. Dosya hiç veritabanı değilse de istisna değil, hata metni döner."""
    try:
        con = sqlite3.connect(f"file:{db_yolu}?mode=ro", uri=True)
        try:
            return con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as e:
        return f"{type(e).__name__}: {e}"


def yedek_olustur(hedef_dizin, simdi=None, db_yolu=None, ek_dizini=None) -> Path:
    """Tek bir yedek zip'i üretir ve yolunu döndürür. Yarım dosya bırakmaz (geçici ad -> yeniden adlandırma)."""
    hedef = Path(hedef_dizin)
    hedef.mkdir(parents=True, exist_ok=True)
    simdi = simdi or datetime.now()
    db_yolu = Path(db_yolu or _db_yolu())
    ek_dizini = Path(ek_dizini if ek_dizini is not None else settings.EK_DIZINI)
    if not db_yolu.exists():
        raise YedekHatasi(f"Veritabanı bulunamadı: {db_yolu}")
    ad = f"cari_yedek_{simdi:%Y%m%d_%H%M%S}.zip"
    nihai, gecici = hedef / ad, hedef / f".{ad}.tmp"
    try:
        with tempfile.TemporaryDirectory() as t:
            anlik = Path(t) / "cari.sqlite3"
            kaynak, hedef_db = sqlite3.connect(db_yolu), sqlite3.connect(anlik)
            try:
                kaynak.backup(hedef_db)                  # tutarlı anlık görüntü (kopyalama değil)
            finally:
                hedef_db.close()
                kaynak.close()
            if _butunluk(anlik) != "ok":
                raise YedekHatasi("Veritabanı bütünlük denetimi başarısız; yedek alınmadı.")
            dosyalar = {"cari.sqlite3": {"sha256": _sha256(anlik), "boyut": anlik.stat().st_size}}
            with zipfile.ZipFile(gecici, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(anlik, "cari.sqlite3")
                if ek_dizini.exists():
                    for p in sorted(ek_dizini.rglob("*")):
                        if p.is_file() and not p.name.startswith("."):
                            rel = "ekler/" + p.relative_to(ek_dizini).as_posix()
                            z.write(p, rel)
                            dosyalar[rel] = {"sha256": _sha256(p), "boyut": p.stat().st_size}
                manifest = {"surum": SURUM, "olusturma": simdi.isoformat(timespec="seconds"),
                            "sayilar": _sayilar(anlik), "dosyalar": dosyalar}
                z.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(gecici, nihai)
    except BaseException:
        if gecici.exists():
            gecici.unlink()
        raise
    return nihai


# ------------------------------------------------------------------ doğrulama / geri yükleme
@dataclass
class Dogrulama:
    ok: bool = True
    hatalar: list = field(default_factory=list)
    uyarilar: list = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def _guvenli_uye(ad: str) -> bool:
    p = Path(ad.replace("\\", "/"))
    return not (p.is_absolute() or ".." in p.parts or ad.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", ad))


def yedek_dogrula(zip_yol) -> Dogrulama:
    """Zip bozuk mu, manifest var mı, her dosyanın özeti tutuyor mu, veritabanı sağlam mı?"""
    d = Dogrulama()
    try:
        z = zipfile.ZipFile(zip_yol)
    except (zipfile.BadZipFile, FileNotFoundError, OSError) as e:
        d.ok, d.hatalar = False, [f"Zip açılamadı: {e}"]
        return d
    with z:
        bozuk = z.testzip()
        if bozuk:
            d.hatalar.append(f"Zip içinde bozuk üye: {bozuk}")
        adlar = z.namelist()
        for a in adlar:
            if not _guvenli_uye(a):
                d.hatalar.append(f"Güvensiz dosya yolu: {a!r}")
        if "MANIFEST.json" not in adlar:
            d.hatalar.append("MANIFEST.json yok.")
        if d.hatalar:
            d.ok = False
            return d
        try:
            d.manifest = json.loads(z.read("MANIFEST.json"))
        except ValueError:
            d.ok, d.hatalar = False, ["MANIFEST.json okunamadı."]
            return d
        beklenen = d.manifest.get("dosyalar", {})
        if "cari.sqlite3" not in beklenen:
            d.hatalar.append("Manifestte veritabanı yok.")
        for ad, bilgi in beklenen.items():
            if ad not in adlar:
                d.hatalar.append(f"Eksik dosya: {ad}")
                continue
            h = hashlib.sha256()
            with z.open(ad) as f:
                for parca in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(parca)
            if h.hexdigest() != bilgi["sha256"]:
                d.hatalar.append(f"Özet tutmuyor (bozulmuş): {ad}")
        for a in adlar:
            if a != "MANIFEST.json" and a not in beklenen and not a.endswith("/"):
                d.uyarilar.append(f"Manifestte olmayan dosya: {a}")
        if not d.hatalar:
            with tempfile.TemporaryDirectory() as t:
                z.extract("cari.sqlite3", t)
                sonuc = _butunluk(Path(t) / "cari.sqlite3")
                if sonuc != "ok":
                    d.hatalar.append(f"Veritabanı bütünlük denetimi: {sonuc}")
    d.ok = not d.hatalar
    return d


def geri_yukle(zip_yol, hedef_dizin) -> dict:
    """
    Yedeği YENİ/BOŞ bir veri klasörüne açar. Çalışan veriyi asla üzerine yazmaz:
    sonra CARI_VERI_DIZINI'ni bu klasöre yönlendirin veya klasörleri değiştirin.
    """
    hedef = Path(hedef_dizin)
    if hedef.exists() and any(hedef.iterdir()):
        raise YedekHatasi(f"Hedef klasör boş değil: {hedef}. Geri yükleme çalışan verinin üzerine yazmaz.")
    d = yedek_dogrula(zip_yol)
    if not d.ok:
        raise YedekHatasi("Yedek doğrulanamadı: " + "; ".join(d.hatalar))
    hedef.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_yol) as z:
        for ad in z.namelist():
            if ad == "MANIFEST.json" or ad.endswith("/"):
                continue
            yol = Path(safe_join(str(hedef), ad))                   # zip-slip koruması
            yol.parent.mkdir(parents=True, exist_ok=True)
            with z.open(ad) as kaynak, open(yol, "wb") as cikti:
                shutil.copyfileobj(kaynak, cikti)
    return {"hedef": hedef, "manifest": d.manifest}


def geri_yukleme_testi(zip_yol) -> dict:
    """
    Yedeği geçici klasöre gerçekten geri yükler; veritabanını açıp sayar ve her ek kaydının
    dosyasının yedekte bulunduğunu doğrular. Geçici klasör silinir. {ok, hatalar, sayilar}
    """
    hatalar = []
    with tempfile.TemporaryDirectory() as t:
        hedef = Path(t) / "veri"
        try:
            geri_yukle(zip_yol, hedef)
        except YedekHatasi as e:
            return {"ok": False, "hatalar": [str(e)], "sayilar": {}}
        db = hedef / "cari.sqlite3"
        sayilar = _sayilar(db)
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            try:
                for (yol,) in con.execute("SELECT yol FROM defter_ek"):
                    if not (hedef / "ekler" / yol).is_file():
                        hatalar.append(f"Ek kaydı var ama dosya yedekte yok: {yol}")
            except sqlite3.Error:
                pass
        finally:
            con.close()
    return {"ok": not hatalar, "hatalar": hatalar, "sayilar": sayilar}


# ------------------------------------------------------------------ saklama (rotasyon)
def _yedek_zamani(ad):
    m = AD_DESENI.match(ad)
    return datetime.strptime(m[1] + m[2], "%Y%m%d%H%M%S") if m else None


def yedek_temizle(dizin, gunluk=None, aylik=None, simdi=None) -> list:
    """
    Son `gunluk` gündeki TÜM yedekler + daha eski aylar için ay başına EN SON yedek (son `aylik` ay) saklanır.
    Gerisi silinir. Yalnızca 'cari_yedek_*.zip' adlı dosyalara dokunur; en yeni yedek ASLA silinmez.
    """
    gunluk = settings.YEDEK_GUNLUK_SAKLA if gunluk is None else gunluk
    aylik = settings.YEDEK_AYLIK_SAKLA if aylik is None else aylik
    simdi = simdi or datetime.now()
    dizin = Path(dizin)
    if not dizin.exists():
        return []
    yedekler = sorted(((_yedek_zamani(p.name), p) for p in dizin.iterdir()
                       if p.is_file() and _yedek_zamani(p.name)), key=lambda x: x[0])
    if not yedekler:
        return []
    sinir_gun = simdi - timedelta(days=gunluk)
    sinir_ay = simdi - timedelta(days=gunluk + 31 * aylik)
    saklanan = {yedekler[-1][1]}
    ay_son = {}
    for zaman, p in yedekler:
        if zaman >= sinir_gun:
            saklanan.add(p)
        elif zaman >= sinir_ay:
            ay_son[(zaman.year, zaman.month)] = p            # sıralı: ay içinde sonuncusu kalır
    saklanan.update(ay_son.values())
    silinen = []
    for _, p in yedekler:
        if p not in saklanan:
            p.unlink()
            silinen.append(p)
    return silinen


# ------------------------------------------------------------------ üst düzey: yedekle + kaydet
def ayni_disk_mi(a, b) -> bool:
    a, b = Path(a).resolve(), Path(b).resolve()
    if os.name == "nt":
        return os.path.splitdrive(str(a))[0].upper() == os.path.splitdrive(str(b))[0].upper()
    try:
        ya = a if a.exists() else a.parent
        yb = b if b.exists() else b.parent
        return os.stat(ya).st_dev == os.stat(yb).st_dev
    except OSError:
        return False


def yedekle(hedefler=None, dogrula=True, test=True, temizle=True, simdi=None, db_yolu=None, ek_dizini=None):
    """
    Her hedefe bir yedek koyar, doğrular, (isteğe bağlı) geri yükleme testi yapar, eskileri temizler ve
    sonucu YedekKaydi olarak kaydeder. Bir hedef başarısız olsa da diğerleri denenir.
    Dönüş: [YedekKaydi]
    """
    from .models import YedekKaydi
    hedefler = [Path(h) for h in (hedefler if hedefler is not None else settings.YEDEK_DIZINLERI)]
    if not hedefler:
        raise YedekHatasi("Yedek hedefi tanımlı değil. CARI_YEDEK_DIZINLERI ayarlayın veya --hedef verin.")
    kayitlar = []
    ilk_zip = None
    veri_dizini = Path(db_yolu).parent if db_yolu else Path(settings.VERI_DIZINI)
    for hedef in hedefler:
        kayit = YedekKaydi(hedef=str(hedef), durum=YedekKaydi.Durum.HATA)
        uyarilar = []
        try:
            if ilk_zip is None:
                zip_yol = yedek_olustur(hedef, simdi, db_yolu, ek_dizini)
                ilk_zip = zip_yol
            else:
                hedef.mkdir(parents=True, exist_ok=True)
                zip_yol = hedef / ilk_zip.name
                gecici = hedef / f".{ilk_zip.name}.tmp"
                shutil.copy2(ilk_zip, gecici)
                os.replace(gecici, zip_yol)
            kayit.dosya, kayit.boyut_bayt = zip_yol.name, zip_yol.stat().st_size
            if ayni_disk_mi(hedef, veri_dizini):
                uyarilar.append("Yedek, verinin bulunduğu diskte. Disk bozulursa ikisi de kaybolur; ayrı disk/USB kullanın.")
            if dogrula:
                d = yedek_dogrula(zip_yol)
                kayit.dogrulandi = d.ok
                if not d.ok:
                    raise YedekHatasi("Doğrulama başarısız: " + "; ".join(d.hatalar))
            if test:
                t = geri_yukleme_testi(zip_yol)
                kayit.geri_yukleme_testi = t["ok"]
                if not t["ok"]:
                    raise YedekHatasi("Geri yükleme testi başarısız: " + "; ".join(t["hatalar"]))
            if temizle:
                silinen = yedek_temizle(hedef, simdi=simdi)
                if silinen:
                    uyarilar.append(f"{len(silinen)} eski yedek saklama kuralı gereği silindi.")
            kayit.durum = YedekKaydi.Durum.UYARI if any("diskte" in u for u in uyarilar) else YedekKaydi.Durum.TAMAM
            kayit.ayrinti = " ".join(uyarilar)
        except Exception as e:                      # bir hedefin hatası diğerlerini durdurmasın
            kayit.durum = YedekKaydi.Durum.HATA
            kayit.ayrinti = f"{type(e).__name__}: {e}"
        kayit.save()
        kayitlar.append(kayit)
    return kayitlar


def yedek_durumu(simdi=None) -> dict:
    """Genel Bakış uyarısı için: son başarılı yedeğin yaşı."""
    from .models import YedekKaydi
    simdi = simdi or timezone.now()
    son = YedekKaydi.objects.exclude(durum=YedekKaydi.Durum.HATA).order_by("-zaman").first()
    if son is None:
        return {"son": None, "gun": None, "uyari": True,
                "mesaj": "Henüz hiç yedek alınmadı. Disk bozulursa tüm veri kaybolur."}
    gun = (simdi - son.zaman).days
    uyari = gun >= settings.YEDEK_UYARI_GUN
    return {"son": son, "gun": gun, "uyari": uyari,
            "mesaj": f"Son başarılı yedek {gun} gün önce." if uyari else ""}
