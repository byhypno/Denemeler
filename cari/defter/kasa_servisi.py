"""Kasa hesapları: özet, aylık akış, kategori dağılımı ve gün sonu kapanışı.

Ofis Kasa (ofis içi küçük harcamalar) cari defterinden TAMAMEN BAĞIMSIZDIR.
"""
from collections import defaultdict
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from . import metin
from .models import Hesap, KasaHareketi, KasaKategori


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
    return {
        "bakiye_kurus": hesap.bakiye_kurus(),
        "bugun_giris": bugun_giris, "bugun_cikis": bugun_cikis,
        "ay_giris": ay_giris, "ay_cikis": ay_cikis,
    }


def kasa_aylik(hesap, yil: int, bugun=None) -> dict:
    bugun = bugun or date.today()
    onceki = hesap.bakiye_kurus(tarih_kadar=date(yil - 1, 12, 31)) if yil > 1 else hesap.acilis_bakiye_kurus
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



# ------------------------------------------------------------------ liste süzgeci, toplam, dışa aktarma, harcayan düzeltme
def hareket_sorgusu(hesap, istek):
    """Kasa hareket listesinin süzgeci (ekran ve Excel aynı kuralı kullanır).

    istek: bas, bit (YYYY-MM-DD), yon, kategori, harcayan ('-' = harcayanı boş), q (açıklama/makbuz/harcayan/kategori;
    büyük-küçük harf ve aksan farkı yok sayılır), iptal ('1' = iptaller de).
    Dönüş: (sorgu, temizlenmiş süzgeç sözlüğü).
    """
    qs = hesap.hareketler.select_related("kategori").order_by("-tarih", "-id")
    f = {k: (istek.get(k, "") or "").strip() for k in ("bas", "bit", "yon", "kategori", "iptal", "harcayan", "q")}
    for alan, op in (("bas", "tarih__gte"), ("bit", "tarih__lte")):
        try:
            if f[alan]:
                qs = qs.filter(**{op: date.fromisoformat(f[alan])})
        except ValueError:
            f[alan] = ""
    if f["yon"] in ("GIRIS", "CIKIS"):
        qs = qs.filter(yon=f["yon"])
    else:
        f["yon"] = ""
    if metin.guvenli_int(f["kategori"]) is not None:
        qs = qs.filter(kategori_id=metin.guvenli_int(f["kategori"]))
    if f["harcayan"] == "-":
        qs = qs.filter(harcayan="")
    elif f["harcayan"]:
        # büyük/küçük harf ve aksan farkı yok sayılır (SQLite LIKE Türkçe harfleri ayırt eder)
        hedef = metin.katla(f["harcayan"])
        ids = [pk for pk, ad in hesap.hareketler.exclude(harcayan="").values_list("pk", "harcayan")
               if metin.katla(ad) == hedef]
        qs = qs.filter(pk__in=ids)
    if f["iptal"] != "1":
        qs = qs.filter(iptal=False)
    if f["q"]:
        ids = [h.pk for h in qs if metin.eslesir(f["q"], h.aciklama, h.makbuz_no, h.harcayan, h.kategori)]
        qs = qs.filter(pk__in=ids)
    return qs, f


def sorgu_toplami(qs) -> dict:
    """Süzülmüş listenin giriş/çıkış/net toplamı (iptal kayıtlar sayılmaz)."""
    gecerli = qs.filter(iptal=False)
    giris = _toplam(gecerli.filter(yon=KasaHareketi.Yon.GIRIS))
    cikis = _toplam(gecerli.filter(yon=KasaHareketi.Yon.CIKIS))
    return {"giris": giris, "cikis": cikis, "net": giris - cikis, "adet": gecerli.count()}


def hareketler_xlsx(hesap, qs) -> bytes:
    """Süzülmüş hareket listesi Excel olarak (tutarlar kuruşlu sayı; '=' ile başlayan metin formül olmaz)."""
    from io import BytesIO

    from openpyxl import Workbook

    from .kasa_rapor import PARA_BICIMI, _lira, _yaz

    wb = Workbook()
    ws = wb.active
    ws.title = "Hareketler"
    basliklar = ["Tarih", "Yön", "Kategori", "Harcayan", "Açıklama", "Makbuz no", "Tutar (₺)", "Durum"]
    for j, b in enumerate(basliklar, 1):
        _yaz(ws, 1, j, b, kalin=True)
    satir = 1
    for h in qs.order_by("tarih", "id"):
        satir += 1
        _yaz(ws, satir, 1, h.tarih).number_format = "DD.MM.YYYY"
        _yaz(ws, satir, 2, h.get_yon_display())
        _yaz(ws, satir, 3, str(h.kategori) if h.kategori else "")
        _yaz(ws, satir, 4, h.harcayan)
        _yaz(ws, satir, 5, h.aciklama)
        _yaz(ws, satir, 6, h.makbuz_no)
        _yaz(ws, satir, 7, _lira(h.tutar_kurus), para=True)
        _yaz(ws, satir, 8, f"İptal: {h.iptal_nedeni}" if h.iptal else "")
    for harf, g in zip("ABCDEFGH", (12, 8, 18, 18, 40, 14, 14, 30)):
        ws.column_dimensions[harf].width = g
    cikti = BytesIO()
    wb.save(cikti)
    return cikti.getvalue()


def harcayan_duzelt(hesap, eski: str, yeni: str) -> dict:
    """
    Bu kasadaki hareketlerde harcayan adını toplu düzeltir (yazım farkı: 'ali' / 'Ali ' -> 'Ali'; ya da boş harcayanı doldurma: eski='-').
    Eşleşme büyük/küçük harf ve aksan farkına bakmaz.
    Her kayıt tek tek kaydedilir; değişiklik işlem günlüğüne düşer. Tutar/tarih/yön değişmez, bakiye etkilenmez.
    Dönüş: {"degisen": n}
    """
    eski, yeni = (eski or "").strip(), " ".join((yeni or "").split())
    if not eski:
        raise ValidationError("Düzeltilecek harcayanı seçin.")
    if not yeni:
        raise ValidationError("Yeni harcayan adını yazın.")
    if len(yeni) > 80:
        raise ValidationError("Harcayan adı en çok 80 karakter olabilir.")
    if eski == "-":
        adaylar = list(hesap.hareketler.filter(harcayan="", iptal=False))
    else:
        hedef = metin.katla(eski)
        adaylar = [h for h in hesap.hareketler.exclude(harcayan="") if metin.katla(h.harcayan) == hedef]
    degisen = 0
    with transaction.atomic():
        for h in adaylar:
            if h.harcayan == yeni:
                continue
            h.harcayan = yeni
            h.save()
            degisen += 1
    return {"degisen": degisen}
