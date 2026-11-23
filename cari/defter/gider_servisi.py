"""Aylık net genel giderler: yıllık tablo, aylık özet, toplu kayıt, önceki aydan kopyalama.

Tutarlar NET (KDV hariç) ve kuruş cinsindendir. Kategori + ay başına TEK kayıt vardır; boş bırakılan alan "gider yok"
demektir ve silme yerine tutar 0 yapılır (geçmiş işlem günlüğünde durur).
"""
from collections import defaultdict
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from . import trend
from .fields import tl_ayristir
from .models import GenelGider, GiderKategori


def kategoriler_yil(yil):
    """Aktif kategoriler + o yıl verisi olan pasif kategoriler (geçmiş tablodan kaybolmasın)."""
    veri_olan = set(GenelGider.objects.filter(yil=yil, tutar_kurus__gt=0).values_list("kategori_id", flat=True))
    return [k for k in GiderKategori.objects.all() if k.aktif or k.pk in veri_olan]


def yillar(bugun=None):
    bugun = bugun or date.today()
    ys = set(GenelGider.objects.values_list("yil", flat=True)) | {bugun.year}
    return sorted(ys)


def yillik_tablo(yil):
    """{"kategoriler": [...], "hucre": {(kat_id, ay): kuruş}, "ay_toplam": [12], "kat_toplam": {kat_id: kuruş}, "toplam": kuruş,
    "notlar": {(kat_id, ay): metin}}"""
    kategoriler = kategoriler_yil(yil)
    hucre, notlar = {}, {}
    ay_toplam = [0] * 12
    kat_toplam = defaultdict(int)
    for g in GenelGider.objects.filter(yil=yil):
        hucre[(g.kategori_id, g.ay)] = g.tutar_kurus
        if g.aciklama:
            notlar[(g.kategori_id, g.ay)] = g.aciklama
        ay_toplam[g.ay - 1] += g.tutar_kurus
        kat_toplam[g.kategori_id] += g.tutar_kurus
    satirlar = [{"kategori": k, "aylar": [hucre.get((k.pk, a), 0) for a in range(1, 13)], "toplam": kat_toplam.get(k.pk, 0)}
                for k in kategoriler]
    return {"kategoriler": kategoriler, "hucre": hucre, "notlar": notlar, "ay_toplam": ay_toplam,
            "kat_toplam": dict(kat_toplam), "toplam": sum(ay_toplam), "satirlar": satirlar}


def onceki_ay(yil, ay):
    return (yil - 1, 12) if ay == 1 else (yil, ay - 1)


def ay_toplami(yil, ay):
    return sum(GenelGider.objects.filter(yil=yil, ay=ay).values_list("tutar_kurus", flat=True))


def ozet(yil, ay, tablo=None):
    """Seçili ay: net toplam, önceki aya göre değişim, yıl başından seçili aya kadar toplam, aylık ortalama
    (yalnızca gider girilen aylar üzerinden), en büyük kalem."""
    tablo = tablo or yillik_tablo(yil)
    secili = tablo["ay_toplam"][ay - 1]
    py, pa = onceki_ay(yil, ay)
    onceki = tablo["ay_toplam"][pa - 1] if py == yil else ay_toplami(py, pa)
    ytd = sum(tablo["ay_toplam"][:ay])
    dolu = [t for t in tablo["ay_toplam"][:ay] if t > 0]
    en_buyuk = None
    adaylar = [(tablo["hucre"].get((k.pk, ay), 0), k) for k in tablo["kategoriler"]]
    adaylar = [a for a in adaylar if a[0] > 0]
    if adaylar:
        en_buyuk = max(adaylar, key=lambda a: a[0])
    return {"secili": secili, "onceki": onceki,
            "degisim": trend.karsilastir(secili, onceki) if (secili or onceki) else None,
            "ytd": ytd, "ortalama": (sum(dolu) // len(dolu)) if dolu else 0, "dolu_ay": len(dolu),
            "en_buyuk": en_buyuk}


def _tutar_coz(metin, kategori):
    metin = (metin or "").strip()
    if not metin:
        return None
    try:
        k = tl_ayristir(metin)
    except ValueError:
        raise ValidationError(f"{kategori.ad}: tutarı 1.234,50 biçiminde girin.")
    if k < 0:
        raise ValidationError(f"{kategori.ad}: gider tutarı eksi olamaz.")
    return k


def kaydet(yil, ay, veri, kategoriler):
    """Bir ayın tüm kategorilerini TEK işlemde kaydeder. `veri`: POST benzeri sözlük (tutar_<id>, not_<id>).
    Hata varsa HİÇBİRİ kaydedilmez (ValidationError, tüm mesajlar). Değişmeyen satıra dokunulmaz (günlük şişmesin).
    Dönüş: değişen satır sayısı."""
    if not (1 <= ay <= 12):
        raise ValidationError("Geçersiz ay.")
    hatalar, isler = [], []
    mevcut = {g.kategori_id: g for g in GenelGider.objects.filter(yil=yil, ay=ay)}
    for k in kategoriler:
        try:
            tutar = _tutar_coz(veri.get(f"tutar_{k.pk}"), k)
        except ValidationError as e:
            hatalar.extend(e.messages)
            continue
        aciklama = (veri.get(f"not_{k.pk}") or "").strip()[:250]
        g = mevcut.get(k.pk)
        if g is None:
            if tutar:                                   # boş/0 ve kayıt yok: oluşturma
                isler.append(("yeni", k, tutar, aciklama))
        else:
            yeni_tutar = 0 if tutar is None else tutar  # boş bırakılan mevcut kayıt: 0 (silinmez)
            if (yeni_tutar, aciklama) != (g.tutar_kurus, g.aciklama):
                isler.append(("degisti", g, yeni_tutar, aciklama))
    if hatalar:
        raise ValidationError(hatalar)
    with transaction.atomic():
        for tur, nesne, tutar, aciklama in isler:
            if tur == "yeni":
                GenelGider.objects.create(kategori=nesne, yil=yil, ay=ay, tutar_kurus=tutar, aciklama=aciklama)
            else:
                nesne.tutar_kurus, nesne.aciklama = tutar, aciklama
                nesne.save()
    return len(isler)


def onceki_aydan_kopyala(yil, ay, kategoriler):
    """Seçili ayda boş (kayıt yok ya da 0) olan kategorilere önceki ayın tutarını yazar (kira gibi sabit kalemler için).
    Dolu satırlara dokunmaz. Dönüş: kopyalanan satır sayısı."""
    py, pa = onceki_ay(yil, ay)
    kaynak = {g.kategori_id: g for g in GenelGider.objects.filter(yil=py, ay=pa, tutar_kurus__gt=0)}
    hedef = {g.kategori_id: g for g in GenelGider.objects.filter(yil=yil, ay=ay)}
    n = 0
    with transaction.atomic():
        for k in kategoriler:
            kg = kaynak.get(k.pk)
            if not kg:
                continue
            h = hedef.get(k.pk)
            if h is None:
                GenelGider.objects.create(kategori=k, yil=yil, ay=ay, tutar_kurus=kg.tutar_kurus, aciklama=kg.aciklama)
                n += 1
            elif h.tutar_kurus == 0:
                h.tutar_kurus, h.aciklama = kg.tutar_kurus, h.aciklama or kg.aciklama
                h.save()
                n += 1
    return n


def yillik_xlsx(yil, tablo=None) -> bytes:
    """Yıllık genel gider tablosu (kategori × 12 ay + toplam) Excel olarak. Formül yok, değerler hazır."""
    from io import BytesIO

    import openpyxl

    from .odeme_listesi import _lira, _yaz
    tablo = tablo or yillik_tablo(yil)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Genel gider {yil}"
    _yaz(ws, 1, 1, f"Aylık Net Genel Giderler — {yil} (KDV hariç, ₺)", kalin=True)
    for i, b in enumerate(["Kategori", *trend.AY_ADLARI, "Toplam"], start=1):
        _yaz(ws, 3, i, b, kalin=True, doldur="DDE6F0")
    r = 4
    for k in tablo["kategoriler"]:
        _yaz(ws, r, 1, k.ad)
        for ay in range(1, 13):
            v = tablo["hucre"].get((k.pk, ay), 0)
            if v:
                _yaz(ws, r, 1 + ay, _lira(v), para=True)
        _yaz(ws, r, 14, _lira(tablo["kat_toplam"].get(k.pk, 0)), kalin=True, para=True)
        r += 1
    _yaz(ws, r, 1, "NET GENEL GİDER", kalin=True)
    for ay in range(1, 13):
        _yaz(ws, r, 1 + ay, _lira(tablo["ay_toplam"][ay - 1]), kalin=True, para=True)
    _yaz(ws, r, 14, _lira(tablo["toplam"]), kalin=True, para=True)
    ws.column_dimensions["A"].width = 24
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
