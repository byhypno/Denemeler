"""Kasa hesapları: özet, aylık akış, kategori dağılımı ve gün sonu kapanışı.

Ofis Kasa (ofis içi küçük harcamalar) cari defterinden TAMAMEN BAĞIMSIZDIR.
"""
from collections import defaultdict
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from . import metin
from .models import GunSonu, Hesap, KasaHareketi, KasaKategori

KASA_FARKI = "Kasa farkı"


def varsayilan_hesap(hesap_id=None, hesaplar=None):
    """`hesaplar`: kullanıcının görebildiği kasalar (verilmezse tüm aktif kasalar)."""
    qs = hesaplar if hesaplar is not None else Hesap.objects.filter(aktif=True, tur=Hesap.Tur.KASA)
    if metin.guvenli_int(hesap_id) is not None:
        h = qs.filter(pk=metin.guvenli_int(hesap_id)).first()
        if h:
            return h
    return qs.order_by("id").first()


def _toplam(qs):
    return qs.aggregate(t=Sum("tutar_kurus"))["t"] or 0


def gun_toplami(hesap, bas, bit):
    qs = hesap.hareketler.filter(iptal=False, tarih__gte=bas, tarih__lte=bit)
    return (_toplam(qs.filter(yon=KasaHareketi.Yon.GIRIS)), _toplam(qs.filter(yon=KasaHareketi.Yon.CIKIS)))


def acik_gunler(hesap, bugun=None):
    """Kapanış bekleyen günler: son kilitten sonra hareket olan, bugünden önceki günler."""
    bugun = bugun or date.today()
    sinir = hesap.kilit_siniri()
    qs = hesap.hareketler.filter(iptal=False, tarih__lt=bugun)
    if sinir:
        qs = qs.filter(tarih__gt=sinir)
    return sorted(set(qs.values_list("tarih", flat=True)))


def harcayanlar(hesap) -> list:
    """Bu kasada daha önce girilmiş harcayan adları (forma öneri olarak), Türkçe alfabe sırasıyla; büyük/küçük harf farkı tek sayılır."""
    gorulen = {}
    for ad in hesap.hareketler.exclude(harcayan="").values_list("harcayan", flat=True):
        gorulen.setdefault(metin.katla(ad), ad)
    return metin.turkce_sirala(gorulen.values())


def kasa_ozeti(hesap, bugun=None) -> dict:
    bugun = bugun or date.today()
    ay_bas = bugun.replace(day=1)
    bugun_giris, bugun_cikis = gun_toplami(hesap, bugun, bugun)
    ay_giris, ay_cikis = gun_toplami(hesap, ay_bas, bugun)
    acik = acik_gunler(hesap, bugun)
    return {
        "bakiye_kurus": hesap.bakiye_kurus(),
        "bugun_giris": bugun_giris, "bugun_cikis": bugun_cikis,
        "ay_giris": ay_giris, "ay_cikis": ay_cikis,
        "kilit_siniri": hesap.kilit_siniri(),
        "acik_gunler": acik,
    }


def kasa_aylik(hesap, yil: int, bugun=None) -> dict:
    bugun = bugun or date.today()
    onceki = hesap.bakiye_kurus(tarih_kadar=date(yil - 1, 12, 31))
    giris, cikis = [0] * 12, [0] * 12
    qs = hesap.hareketler.filter(iptal=False, tarih__year=yil)
    for tarih, yon, tutar in qs.values_list("tarih", "yon", "tutar_kurus"):
        (giris if yon == KasaHareketi.Yon.GIRIS else cikis)[tarih.month - 1] += tutar
    bakiye, ay_sonu = onceki, []
    for i in range(12):
        bakiye += giris[i] - cikis[i]
        ay_sonu.append(None if (yil, i + 1) > (bugun.year, bugun.month) else bakiye)
    return {"giris": giris, "cikis": cikis, "ay_sonu": ay_sonu}


def kasa_yillari(hesap, bugun=None):
    bugun = bugun or date.today()
    yillar = sorted({d.year for d in hesap.hareketler.filter(iptal=False).dates("tarih", "year")})
    return yillar or [bugun.year]


def kategori_dagilimi(hesap, yil: int, yon=KasaHareketi.Yon.CIKIS, n=8):
    """[(kategori_adı, toplam_kurus)] büyükten küçüğe; n'den sonrası 'Diğer' altında toplanır."""
    toplam = defaultdict(int)
    qs = hesap.hareketler.filter(iptal=False, yon=yon, tarih__year=yil).select_related("kategori")
    for h in qs:
        toplam[h.kategori.ad if h.kategori else "Kategorisiz"] += h.tutar_kurus
    sirali = sorted(toplam.items(), key=lambda x: -x[1])
    if len(sirali) > n:
        sirali = sirali[:n - 1] + [("Diğer", sum(t for _, t in sirali[n - 1:]))]
    return sirali


def en_buyuk_cikislar(hesap, yil: int, n=10):
    return list(hesap.hareketler.filter(iptal=False, yon=KasaHareketi.Yon.CIKIS, tarih__year=yil)
                .select_related("kategori").order_by("-tutar_kurus", "-tarih")[:n])


def hareketler_bakiyeli(hesap):
    """{hareket_pk: o harekettten sonraki bakiye} — (tarih, id) sırasıyla, iptaller hariç."""
    bakiye, sonuc = hesap.acilis_bakiye_kurus, {}
    for h in hesap.hareketler.filter(iptal=False).order_by("tarih", "id"):
        bakiye += h.tutar_kurus if h.yon == KasaHareketi.Yon.GIRIS else -h.tutar_kurus
        sonuc[h.pk] = bakiye
    return sonuc


# ---------------------------------------------------------------- Gün sonu kapanışı
def gun_sonu_beklenen(hesap, tarih) -> int:
    return hesap.bakiye_kurus(tarih_kadar=tarih)


@transaction.atomic
def gun_sonu_kapat(hesap, tarih, sayilan_kurus: int, aciklama="", farki_isle=False, bugun=None) -> GunSonu:
    """
    `tarih` ve öncesini kilitler. Sayılan nakit ile kayıtlı bakiye arasındaki fark GunSonu'ya yazılır;
    `farki_isle` ise fark, kapanış gününe 'Kasa farkı' kategorili bir hareket olarak işlenir.
    """
    bugun = bugun or date.today()
    if tarih > bugun:
        raise ValidationError("Gelecek bir gün kapatılamaz.")
    sinir = hesap.kilit_siniri()
    if sinir and tarih <= sinir:
        raise ValidationError(f"Kasa {sinir:%d.%m.%Y} tarihine kadar zaten kapatılmış.")
    if sayilan_kurus is None or sayilan_kurus < 0:
        raise ValidationError("Sayılan nakit eksi olamaz.")
    beklenen = gun_sonu_beklenen(hesap, tarih)
    fark = sayilan_kurus - beklenen
    islendi = False
    if farki_isle and fark != 0:
        kat, _ = KasaKategori.objects.get_or_create(
            ad=KASA_FARKI, defaults={"tur": KasaKategori.Tur.GIDER})
        KasaHareketi.objects.create(
            hesap=hesap, tarih=tarih, kategori=kat,
            yon=KasaHareketi.Yon.GIRIS if fark > 0 else KasaHareketi.Yon.CIKIS,
            tutar_kurus=abs(fark), aciklama=f"Gün sonu kasa farkı ({tarih:%d.%m.%Y})")
        islendi = True
    return GunSonu.objects.create(
        hesap=hesap, tarih=tarih, beklenen_kurus=beklenen, sayilan_kurus=sayilan_kurus,
        fark_kurus=fark, fark_islendi=islendi, aciklama=aciklama[:250], kilitli=True)
