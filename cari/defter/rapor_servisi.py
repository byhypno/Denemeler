"""Aylık özet raporu: tedarikçi hareketleri, net genel gider ve Ofis Kasa harcamaları (ay sonu itibarıyla).

Tutarlar kuruş. Kaynak: cari hareketleri (iptaller hariç), Genel giderler, kasa hareketleri (iptaller hariç).
Rapor, program verisinden HESAPLANIR; ayrı bir veri girişi yoktur.
"""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
from django.db.models import Sum

from . import gider_servisi as gs
from . import metin, services, trend
from .models import Belge, Hesap, KasaHareketi

ALIS = (Belge.Tur.ALIS_FISI, Belge.Tur.ALIS_FATURASI)


def ay_araligi(yil, ay):
    return date(yil, ay, 1), date(yil, ay, calendar.monthrange(yil, ay)[1])


def _onceki(yil, ay):
    return (yil - 1, 12) if ay == 1 else (yil, ay - 1)


def _tedarikciler(yil, ay):
    bas, son = ay_araligi(yil, ay)
    onceki_gun = date.fromordinal(bas.toordinal() - 1)
    satir = defaultdict(lambda: {"alis": 0, "odeme": 0, "iade": 0, "diger": 0})
    qs = (Belge.objects.filter(iptal=False, tarih__range=(bas, son)).values("cari", "tur").annotate(t=Sum("tutar_kurus")))
    for r in qs:
        s, t = satir[r["cari"]], r["t"]
        if r["tur"] in ALIS:
            s["alis"] += t
        elif r["tur"] == Belge.Tur.ODEME:
            s["odeme"] += t
        elif r["tur"] == Belge.Tur.IADE:
            s["iade"] += t
        else:                                              # açılış/devir ve düzeltmeler: işaretli
            s["diger"] += t if r["tur"] in Belge.ARTIRAN else -t
    acilis = dict((c.pk, b) for c, b in services.cari_bakiyeleri(onceki_gun))
    kapanis = dict((c.pk, b) for c, b in services.cari_bakiyeleri(son))
    cariler = {c.pk: c for c, _ in services.cari_bakiyeleri(son)}
    satirlar = []
    for pk, c in cariler.items():
        s = satir.get(pk, {"alis": 0, "odeme": 0, "iade": 0, "diger": 0})
        ac, kap = acilis.get(pk, 0), kapanis.get(pk, 0)
        if not (any(s.values()) or ac or kap):
            continue
        satirlar.append({"cari": c, **s, "acilis": ac, "kapanis": kap})
    satirlar.sort(key=lambda r: (-r["kapanis"], metin.katla(r["cari"].unvan)))
    toplam = {k: sum(r[k] for r in satirlar) for k in ("alis", "odeme", "iade", "diger", "acilis", "kapanis")}
    return satirlar, toplam


def _kasa(yil, ay):
    bas, son = ay_araligi(yil, ay)
    sonuc = []
    for h in Hesap.objects.filter(aktif=True, tur=Hesap.Tur.KASA).order_by("id"):
        qs = h.hareketler.filter(iptal=False, tarih__range=(bas, son))
        giris = qs.filter(yon=KasaHareketi.Yon.GIRIS).aggregate(t=Sum("tutar_kurus"))["t"] or 0
        cikis_kat = defaultdict(int)
        for k in qs.filter(yon=KasaHareketi.Yon.CIKIS).select_related("kategori"):
            cikis_kat[k.kategori.ad if k.kategori else "Kategorisiz"] += k.tutar_kurus
        sonuc.append({"hesap": h, "giris": giris, "cikis": sum(cikis_kat.values()),
                      "kategoriler": sorted(cikis_kat.items(), key=lambda x: -x[1]),
                      "kapanis": h.bakiye_kurus(tarih_kadar=son)})
    return sonuc


def aylik_rapor(yil, ay, kasa_dahil=True):
    bas, son = ay_araligi(yil, ay)
    tedarikciler, t_toplam = _tedarikciler(yil, ay)
    py, pa = _onceki(yil, ay)
    onceki_ted = _tedarikciler(py, pa)[1]
    tablo = gs.yillik_tablo(yil)
    gider = gs.ozet(yil, ay, tablo)
    kalemler = [(k, tablo["hucre"].get((k.pk, ay), 0)) for k in tablo["kategoriler"]]
    kalemler = [(k, v) for k, v in kalemler if v]
    borclu_pozitif = sum(r["kapanis"] for r in tedarikciler if r["kapanis"] > 0)
    avans = -sum(r["kapanis"] for r in tedarikciler if r["kapanis"] < 0)
    gy_ted = _tedarikciler(yil - 1, ay)[1] if yil > 2000 else {"alis": 0, "odeme": 0}
    gy_gider = gs.ay_toplami(yil - 1, ay) if yil > 2000 else 0
    gecen_yil = [(ad, bu, gy, trend.karsilastir(bu, gy) if (bu or gy) else None) for ad, bu, gy in (
        ("Tedarikçi alışları", t_toplam["alis"], gy_ted["alis"]),
        ("Tedarikçilere ödenen", t_toplam["odeme"], gy_ted["odeme"]),
        ("Net genel gider", gider["secili"], gy_gider))]
    return {
        "gecen_yil": gecen_yil if any(gy for _, _, gy, _ in gecen_yil) else None,
        "yil": yil, "ay": ay, "ay_adi": trend.AY_ADLARI[ay - 1], "bas": bas, "son": son,
        "tedarikciler": tedarikciler, "ted_toplam": t_toplam,
        "ted_degisim": {"alis": trend.karsilastir(t_toplam["alis"], onceki_ted["alis"]) if (t_toplam["alis"] or onceki_ted["alis"]) else None,
                        "odeme": trend.karsilastir(t_toplam["odeme"], onceki_ted["odeme"]) if (t_toplam["odeme"] or onceki_ted["odeme"]) else None},
        "ay_sonu_borc": borclu_pozitif, "ay_sonu_avans": avans,
        "gider_kalemleri": kalemler, "gider": gider,
        "kasa": _kasa(yil, ay) if kasa_dahil else None,
    }


def _lira(k):
    return Decimal(int(k)) / 100


def rapor_xlsx(r) -> bytes:
    """Rapor Excel olarak: Özet, Tedarikçiler, Genel gider, Kasa sayfaları. Formül yok, değerler hazır."""
    from .odeme_listesi import _yaz
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Özet"
    _yaz(ws, 1, 1, f"Aylık Özet — {r['ay_adi']} {r['yil']}", kalin=True)
    satirlar = [("Net genel gider (KDV hariç)", r["gider"]["secili"]), ("Tedarikçi alışları", r["ted_toplam"]["alis"]),
                ("Tedarikçilere ödenen", r["ted_toplam"]["odeme"]), ("Tedarikçi iadeleri", r["ted_toplam"]["iade"]),
                ("Ay sonu tedarikçi borcu", r["ay_sonu_borc"]), ("Ay sonu fazla ödeme (avans)", r["ay_sonu_avans"])]
    for k in (r["kasa"] or []):
        satirlar.append((f"{k['hesap'].ad}: ay çıkışı", k["cikis"]))
    for i, (ad, v) in enumerate(satirlar, start=3):
        _yaz(ws, i, 1, ad)
        _yaz(ws, i, 2, _lira(v), para=True)
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 18

    ws = wb.create_sheet("Tedarikçiler")
    for i, b in enumerate(["Tedarikçi", "Ay başı bakiye", "Alışlar", "İadeler", "Ödemeler", "Devir/düzeltme", "Ay sonu bakiye"], start=1):
        _yaz(ws, 1, i, b, kalin=True, doldur="DDE6F0")
    for n, s in enumerate(r["tedarikciler"], start=2):
        _yaz(ws, n, 1, s["cari"].unvan)
        for i, k in enumerate(("acilis", "alis", "iade", "odeme", "diger", "kapanis"), start=2):
            _yaz(ws, n, i, _lira(s[k]), para=True)
    n = len(r["tedarikciler"]) + 2
    _yaz(ws, n, 1, "TOPLAM", kalin=True)
    for i, k in enumerate(("acilis", "alis", "iade", "odeme", "diger", "kapanis"), start=2):
        _yaz(ws, n, i, _lira(r["ted_toplam"][k]), kalin=True, para=True)
    ws.column_dimensions["A"].width = 34

    ws = wb.create_sheet("Genel gider")
    _yaz(ws, 1, 1, "Kategori", kalin=True, doldur="DDE6F0")
    _yaz(ws, 1, 2, "Net tutar (KDV hariç)", kalin=True, doldur="DDE6F0")
    for n, (k, v) in enumerate(r["gider_kalemleri"], start=2):
        _yaz(ws, n, 1, k.ad)
        _yaz(ws, n, 2, _lira(v), para=True)
    n = len(r["gider_kalemleri"]) + 2
    _yaz(ws, n, 1, "NET GENEL GİDER", kalin=True)
    _yaz(ws, n, 2, _lira(r["gider"]["secili"]), kalin=True, para=True)
    ws.column_dimensions["A"].width = 30

    if r["kasa"] is not None:
        ws = wb.create_sheet("Kasa")
        n = 1
        for k in r["kasa"]:
            _yaz(ws, n, 1, f"{k['hesap'].ad} — ay girişi", kalin=True)
            _yaz(ws, n, 2, _lira(k["giris"]), para=True)
            _yaz(ws, n + 1, 1, "Ay çıkışı", kalin=True)
            _yaz(ws, n + 1, 2, _lira(k["cikis"]), para=True)
            _yaz(ws, n + 2, 1, "Ay sonu bakiye", kalin=True)
            _yaz(ws, n + 2, 2, _lira(k["kapanis"]), para=True)
            n += 4
            for ad, v in k["kategoriler"]:
                _yaz(ws, n, 1, f"  {ad}")
                _yaz(ws, n, 2, _lira(v), para=True)
                n += 1
            n += 1
        ws.column_dimensions["A"].width = 34
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
