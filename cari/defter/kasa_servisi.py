"""Kasa hesapları: özet, aylık akış, kategori dağılımı, gün sonu kapanışı ve Cari Kasa kontrolü.

Ofis Kasa, cari defterinden TAMAMEN BAĞIMSIZDIR. "Cari Kasa" türü hesaplarda cari/ilgili ödeme
yalnızca bilgi ve referans amaçlıdır: kasa hareketi cari bakiyesini, cari ödemesi kasa bakiyesini
ASLA otomatik değiştirmez; burada yalnızca tutarsızlıkları listeler ve (onayla) referans bağı kurarız.
"""
import calendar
from collections import defaultdict
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import Belge, GunSonu, Hesap, KasaHareketi, KasaKategori

KASA_FARKI = "Kasa farkı"
ESLESME_GUN = 3


def varsayilan_hesap(hesap_id=None):
    qs = Hesap.objects.filter(aktif=True, tur=Hesap.Tur.KASA)
    if hesap_id and str(hesap_id).isdigit():
        h = qs.filter(pk=int(hesap_id)).first()
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


# ---------------------------------------------------------------- Cari Kasa ↔ cari ödemesi kontrolü
def _yakin(a, b):
    return abs((a - b).days) <= ESLESME_GUN


def kasa_kontrol(hesap=None) -> dict:
    """
    Yalnızca cari bağlantılı kasalar (Cari Kasa) için:
    1) Nakit ödeme olarak girilmiş ama kasa çıkışı bağlanmamış cari ödemeleri
    2) Cari seçilmiş ama ilgili cari ödemesi bağlanmamış kasa çıkışları
    Aynı cari + aynı tutar + ±3 gün eşleşmesi varsa ve tek aday ise 'öneri' olarak verilir.
    """
    if hesap is not None and not hesap.cari_bagli:
        return {"nakit_kasasiz": [], "kasa_odemesiz": [], "adet": 0}
    bagli_odemeler = set(KasaHareketi.objects.filter(iptal=False, ilgili_odeme__isnull=False)
                         .values_list("ilgili_odeme_id", flat=True))
    cikislar = KasaHareketi.objects.filter(
        iptal=False, yon=KasaHareketi.Yon.CIKIS, cari__isnull=False, ilgili_odeme__isnull=True,
        hesap__cari_bagli=True).select_related("cari", "hesap", "kategori")
    if hesap:
        cikislar = cikislar.filter(hesap=hesap)
    cikislar = list(cikislar)
    odemeler = list(Belge.objects.filter(tur=Belge.Tur.ODEME, iptal=False).select_related("cari")
                    .exclude(pk__in=bagli_odemeler))

    def adaylar_odeme(o):
        return [c for c in cikislar if c.cari_id == o.cari_id and c.tutar_kurus == o.tutar_kurus
                and _yakin(c.tarih, o.tarih)]

    def adaylar_cikis(c):
        return [o for o in odemeler if o.cari_id == c.cari_id and o.tutar_kurus == c.tutar_kurus
                and _yakin(c.tarih, o.tarih)]

    nakit_kasasiz = []
    for o in odemeler:
        if o.odeme_sekli != Belge.OdemeSekli.NAKIT:
            continue
        a = adaylar_odeme(o)
        nakit_kasasiz.append({"odeme": o, "oneri": a[0] if len(a) == 1 else None, "aday_sayisi": len(a)})
    kasa_odemesiz = []
    for c in cikislar:
        a = adaylar_cikis(c)
        kasa_odemesiz.append({"hareket": c, "oneri": a[0] if len(a) == 1 else None, "aday_sayisi": len(a)})
    return {"nakit_kasasiz": nakit_kasasiz, "kasa_odemesiz": kasa_odemesiz,
            "adet": len(nakit_kasasiz) + len(kasa_odemesiz)}


def eslestir(hareket_id: int, odeme_id: int) -> KasaHareketi:
    """Yalnızca bir REFERANS bağı kurar; hiçbir tutarı değiştirmez (kapalı günlerde de serbesttir)."""
    h = KasaHareketi.objects.select_related("hesap").get(pk=hareket_id, iptal=False)
    o = Belge.objects.get(pk=odeme_id, tur=Belge.Tur.ODEME, iptal=False)
    if not h.hesap.cari_bagli:
        raise ValidationError("Bu kasa cari defterinden bağımsızdır; eşleştirme yapılamaz.")
    if h.cari_id != o.cari_id:
        raise ValidationError("Kasa hareketi ve cari ödemesi aynı cariye ait olmalı.")
    if KasaHareketi.objects.filter(iptal=False, ilgili_odeme=o).exclude(pk=h.pk).exists():
        raise ValidationError("Bu cari ödemesi başka bir kasa hareketine zaten bağlı.")
    KasaHareketi.objects.filter(pk=h.pk).update(ilgili_odeme=o)   # save() kilit kontrolünü atlar
    h.refresh_from_db()
    from . import gunluk
    gunluk.yaz("DEGISTI", "KasaHareketi", h, {"İlgili cari ödemesi (isteğe bağlı)": [None, str(o)]},
               ayrinti="Cari ödemesi ile kasa hareketi eşleştirildi (yalnızca referans).")
    return h
