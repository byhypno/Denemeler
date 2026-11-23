"""Ek dosya deposu.

Güvenlik ilkeleri
- İzin listesi: yalnızca PDF, JPG, PNG, GIF, WEBP, XLSX, DOCX. HTML/SVG/JS/EXE vb. reddedilir.
- Uzantıya güvenilmez: dosyanın ilk baytları (imza) uzantıyla uyuşmalı.
- Dosya adı kullanıcıdan gelir: yol bileşenleri ve denetim karakterleri temizlenir; diskteki ad
  yalnızca içerik hash'idir, yani kullanıcı girdisi dosya yolunu etkileyemez.
- Dosyalar statik/medya adresiyle sunulmaz; yalnızca giriş gerektiren bir görünümle verilir.
- Silinmez: kaldırılan ek işaretlenir, dosya diskte kalır.
"""
import hashlib
import os
import re
import unicodedata
import zipfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils._os import safe_join

from .models import Belge, Cari, EkstreMutabakat, Ek, KasaHareketi

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _zip_ofis(veri: bytes) -> bool:
    if not veri.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(BytesIO(veri)) as z:          # yalnızca ad listesi okunur, açılmaz
            return "[Content_Types].xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


IZINLI = {
    ".pdf": ("application/pdf", lambda v: v.startswith(b"%PDF-")),
    ".jpg": ("image/jpeg", lambda v: v.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda v: v.startswith(b"\xff\xd8\xff")),
    ".png": ("image/png", lambda v: v.startswith(b"\x89PNG\r\n\x1a\n")),
    ".gif": ("image/gif", lambda v: v.startswith((b"GIF87a", b"GIF89a"))),
    ".webp": ("image/webp", lambda v: v[:4] == b"RIFF" and v[8:12] == b"WEBP"),
    ".xlsx": (XLSX, _zip_ofis),
    ".docx": (DOCX, _zip_ofis),
}
ONIZLENEBILIR = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
GORSEL = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SAHIPLER = {"belge": Belge, "kasa": KasaHareketi, "mutabakat": EkstreMutabakat, "cari": Cari}
SAHIP_ALAN = {Belge: "belge", KasaHareketi: "kasa_hareketi", EkstreMutabakat: "mutabakat", Cari: "cari"}
SAHIP_KISA = {"belge": "belge", "kasa_hareketi": "kasa", "mutabakat": "mutabakat", "cari": "cari"}


class EkHatasi(ValueError):
    """Kullanıcıya gösterilebilecek, anlaşılır dosya hatası."""


def izinli_uzantilar() -> str:
    return ", ".join(sorted({u.lstrip(".") for u in IZINLI if u != ".jpeg"}))


def temiz_ad(ad: str) -> str:
    """Yol bileşenlerini ve denetim karakterlerini atar; uzantıyı korur; uzunluğu sınırlar."""
    ad = unicodedata.normalize("NFC", str(ad or "")).replace("\\", "/").split("/")[-1]
    ad = re.sub(r"[\x00-\x1f\x7f]", "", ad).strip().strip(".")
    ad = re.sub(r"\s+", " ", ad)
    if not ad:
        return "dosya"
    govde, nokta, uzanti = ad.rpartition(".")
    if not nokta:
        return ad[:150]
    return (govde[:150 - len(uzanti) - 1] + "." + uzanti) if len(ad) > 150 else ad


def _sahip_filtresi(sahip) -> dict:
    alan = SAHIP_ALAN.get(type(sahip))
    if alan is None:
        raise EkHatasi("Bu kayıt türüne dosya eklenemez.")
    return {alan: sahip}


def depo_yolu(ek: Ek) -> Path:
    """Diskteki dosyanın tam yolu (depo dışına çıkamaz)."""
    return Path(safe_join(str(settings.EK_DIZINI), ek.yol))


def _oku(dosya) -> bytes:
    maks = settings.EK_MAX_BAYT
    tampon, toplam = BytesIO(), 0
    for parca in dosya.chunks():
        toplam += len(parca)
        if toplam > maks:
            raise EkHatasi(f"Dosya en fazla {maks // (1024 * 1024)} MB olabilir.")
        tampon.write(parca)
    return tampon.getvalue()


def _yaz(yol: Path, veri: bytes):
    yol.parent.mkdir(parents=True, exist_ok=True)
    if yol.exists() and yol.stat().st_size == len(veri):
        return                                           # aynı içerik zaten depoda
    gecici = yol.with_name(f".{yol.name}.tmp")
    with open(gecici, "wb") as f:
        f.write(veri)
    try:
        os.chmod(gecici, 0o600)
    except OSError:
        pass
    os.replace(gecici, yol)                              # atomik: yarım dosya kalmaz


@transaction.atomic
def ek_ekle(sahip, dosya, aciklama: str = "", yukleyen: str = "") -> Ek:
    filtre = _sahip_filtresi(sahip)
    ad = temiz_ad(getattr(dosya, "name", ""))
    uzanti = os.path.splitext(ad)[1].lower()
    if uzanti not in IZINLI:
        raise EkHatasi(f"'{ad}': bu dosya türüne izin verilmiyor. İzinli türler: {izinli_uzantilar()}.")
    veri = _oku(dosya)
    if not veri:
        raise EkHatasi(f"'{ad}': dosya boş.")
    tur, imza_tamam = IZINLI[uzanti]
    if not imza_tamam(veri):
        raise EkHatasi(f"'{ad}': dosya içeriği {uzanti} türüyle uyuşmuyor (bozuk veya uzantısı değiştirilmiş).")
    sha = hashlib.sha256(veri).hexdigest()
    if Ek.objects.filter(sha256=sha, kaldirildi=False, **filtre).exists():
        raise EkHatasi(f"'{ad}': bu dosya zaten ekli.")
    yol_rel = f"{sha[:2]}/{sha}{'.jpg' if uzanti == '.jpeg' else uzanti}"
    _yaz(Path(safe_join(str(settings.EK_DIZINI), yol_rel)), veri)
    return Ek.objects.create(
        orijinal_ad=ad, icerik_turu=tur, boyut_bayt=len(veri), sha256=sha, yol=yol_rel,
        aciklama=(aciklama or "").strip()[:250], yukleyen=(yukleyen or "")[:150], **filtre)


def ek_kaldir(ek: Ek, neden: str) -> Ek:
    neden = (neden or "").strip()
    if not neden:
        raise EkHatasi("Kaldırma nedeni yazın.")
    if ek.kaldirildi:
        raise EkHatasi("Ek zaten kaldırılmış.")
    ek.kaldirildi, ek.kaldirma_nedeni, ek.kaldirma_zamani = True, neden[:250], timezone.now()
    ek.save(update_fields=["kaldirildi", "kaldirma_nedeni", "kaldirma_zamani"])
    return ek


def ekleri_listele(sahip, kaldirilanlar=False):
    qs = Ek.objects.filter(**_sahip_filtresi(sahip))
    return qs if kaldirilanlar else qs.filter(kaldirildi=False)


def ek_sayilari(sahipler, alan: str) -> dict:
    """{sahip_pk: aktif ek sayısı} — listelerde 📎 göstermek için tek sorgu."""
    from django.db.models import Count
    satirlar = (Ek.objects.filter(kaldirildi=False, **{f"{alan}__in": list(sahipler)})
                .values(alan).annotate(n=Count("id")))
    return {s[alan]: s["n"] for s in satirlar}


def depo_dogrula() -> dict:
    """Veritabanı ↔ disk tutarlılığı: eksik dosya, bozuk (hash tutmayan) dosya, kayıtsız (yetim) dosya."""
    kok = Path(settings.EK_DIZINI)
    eksik, bozuk, bilinen = [], [], set()
    for ek in Ek.objects.all().order_by("id"):
        yol = depo_yolu(ek)
        bilinen.add(yol.resolve())
        if not yol.exists():
            eksik.append(ek)
            continue
        h = hashlib.sha256()
        with open(yol, "rb") as f:
            for parca in iter(lambda: f.read(1024 * 1024), b""):
                h.update(parca)
        if h.hexdigest() != ek.sha256:
            bozuk.append(ek)
    yetim = []
    if kok.exists():
        for p in kok.rglob("*"):
            if p.is_file() and not p.name.startswith(".") and p.resolve() not in bilinen:
                yetim.append(p)
    return {"eksik": eksik, "bozuk": bozuk, "yetim": yetim, "toplam": Ek.objects.count()}
