"""KDV / tevkifat hesabı. Tüm tutarlar tamsayı kuruş; yuvarlama: yarım yukarı."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import models


class KdvModu(models.TextChoices):
    BILINMIYOR = "BILINMIYOR", "KDV bilinmiyor"
    HARIC = "HARIC", "Girilen tutar KDV hariç"
    DAHIL = "DAHIL", "Girilen tutar KDV dahil"


def _yuvarla(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def kdv_hesapla(tutar_kurus: int, oran, mod: str, tevkifat_orani=None) -> dict:
    """
    HARIC: tutar = matrah.   DAHIL: tutar = matrah + KDV.
    tevkifat_orani: KDV'nin yüzde kaçı alıcı tarafından beyan/ödenir (örn. 50, 90). Yalnızca HARIC.
    odenecek_kurus = tedarikçiye ödenecek = matrah + KDV - tevkifat (cari bakiyeyi etkileyen tutar).
    """
    oran = Decimal(str(oran))
    t = Decimal(int(tutar_kurus))
    if mod == KdvModu.HARIC:
        matrah = int(tutar_kurus)
        kdv = _yuvarla(t * oran / 100)
    elif mod == KdvModu.DAHIL:
        matrah = _yuvarla(t * 100 / (100 + oran))
        kdv = int(tutar_kurus) - matrah
    else:
        raise ValueError("KDV modu HARIC veya DAHIL olmalı")
    tevkifat = 0
    if tevkifat_orani:
        if mod != KdvModu.HARIC:
            raise ValueError("Tevkifat yalnızca KDV hariç girişte hesaplanır")
        tevkifat = _yuvarla(Decimal(kdv) * Decimal(str(tevkifat_orani)) / 100)
    return {
        "matrah_kurus": matrah,
        "kdv_kurus": kdv,
        "tevkifat_kurus": tevkifat,
        "fatura_toplami_kurus": matrah + kdv,
        "odenecek_kurus": matrah + kdv - tevkifat,
    }


def oranlari_dogrula(kdv_orani, tevkifat_orani=None):
    """KDV ve tevkifat oranı yüzde olarak 0–100 arasında olmalı (aksi halde sıfıra bölme / veritabanı kısıtı hatası olurdu).
    Geçersizse ValueError(mesaj)."""
    if kdv_orani is not None and not (0 <= kdv_orani <= 100):
        raise ValueError("KDV oranı 0 ile 100 arasında olmalı.")
    if tevkifat_orani is not None and not (0 <= tevkifat_orani <= 100):
        raise ValueError("Tevkifat oranı 0 ile 100 arasında olmalı (KDV'nin yüzdesi, ör. 50).")
