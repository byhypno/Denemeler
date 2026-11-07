"""Cari ödeme listeleri: 'Ödenecekler' (açık borç) ve 'Yapılan ödemeler'; ekran, yazdırma ve Excel çıktısı."""
from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import services
from .models import Belge

PARA_BICIMI = "#,##0.00"
KOVA_ETIKETLERI = services.KOVALAR


def _lira(kurus):
    """Excel için tam kuruşlu sayı (Decimal; kayan nokta yok)."""
    return Decimal(int(kurus)) / 100


def odenecekler(bugun=None, cari=None) -> dict:
    bugun = bugun or date.today()
    satirlar, avanslar = services.cari_bazli_acik_borc(bugun, cari)
    return {
        "bugun": bugun, "satirlar": satirlar, "avanslar": avanslar,
        "toplam_kurus": sum(r["toplam_kurus"] for r in satirlar),
        "kovalar": [sum(r["kovalar"][i] for r in satirlar) for i in range(4)],
        "vadesi_gecmis_kurus": sum(r["vadesi_gecmis_kurus"] for r in satirlar),
        "vade_tanimli": any(r["vade_tanimli"] for r in satirlar),
    }


def yapilan_odemeler(bas, bit, cari=None, sekil="") -> dict:
    qs = (Belge.objects.filter(tur=Belge.Tur.ODEME, iptal=False, tarih__gte=bas, tarih__lte=bit)
          .select_related("cari").order_by("cari__unvan", "tarih", "id"))
    if cari:
        qs = qs.filter(cari=cari)
    if sekil:
        qs = qs.filter(odeme_sekli=sekil)
    gruplar, sekil_toplam = [], {}
    for b in qs:
        if not gruplar or gruplar[-1]["cari"].pk != b.cari_id:
            gruplar.append({"cari": b.cari, "belgeler": [], "toplam_kurus": 0})
        gruplar[-1]["belgeler"].append(b)
        gruplar[-1]["toplam_kurus"] += b.tutar_kurus
        etiket = b.get_odeme_sekli_display() or "Belirtilmemiş"
        sekil_toplam[etiket] = sekil_toplam.get(etiket, 0) + b.tutar_kurus
    return {
        "bas": bas, "bit": bit, "gruplar": gruplar,
        "adet": sum(len(g["belgeler"]) for g in gruplar),
        "toplam_kurus": sum(g["toplam_kurus"] for g in gruplar),
        "sekil_toplamlari": sorted(sekil_toplam.items(), key=lambda x: -x[1]),
    }


# ------------------------------------------------------------------ Excel
def _yaz(ws, satir, sutun, deger, kalin=False, para=False, doldur=None):
    if isinstance(deger, str):
        deger = ILLEGAL_CHARACTERS_RE.sub("", deger)   # \x0b gibi denetim karakterleri Excel dosyasını bozar
    h = ws.cell(row=satir, column=sutun, value=deger)
    if isinstance(deger, str):
        h.data_type = "s"          # '=' ile başlayan metin formüle dönüşmesin (Excel formül enjeksiyonu)
    if kalin:
        h.font = Font(bold=True)
    if para:
        h.number_format = PARA_BICIMI
        h.alignment = Alignment(horizontal="right")
    if doldur:
        h.fill = PatternFill("solid", fgColor=doldur)
    return h


def _genislik(ws, genislikler):
    for i, g in enumerate(genislikler, start=1):
        ws.column_dimensions[get_column_letter(i)].width = g


def odenecekler_xlsx(veri: dict) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ödenecekler"
    _yaz(ws, 1, 1, f"Ödenecekler Listesi — {veri['bugun']:%d.%m.%Y}", kalin=True)
    _yaz(ws, 2, 1, "Açık borç, ödemelerin en eski borca mahsup edildiği (FIFO) varsayımıyla hesaplanmıştır.")
    baslik = ["Cari", "Açık borç (₺)", *[f"{k} (₺)" for k in KOVA_ETIKETLERI], "En eski belge",
              "Yaş (gün)", "Vadesi geçmiş (₺)", "Planlanan ödeme (₺)", "Not"]
    for i, b in enumerate(baslik, start=1):
        _yaz(ws, 4, i, b, kalin=True, doldur="DDE6F0")
    r = 5
    for s in veri["satirlar"]:
        _yaz(ws, r, 1, s["cari"].unvan)
        _yaz(ws, r, 2, _lira(s["toplam_kurus"]), para=True)
        for i, k in enumerate(s["kovalar"]):
            _yaz(ws, r, 3 + i, _lira(k), para=True)
        ws.cell(row=r, column=7, value=s["en_eski_tarih"]).number_format = "DD.MM.YYYY"
        ws.cell(row=r, column=8, value=s["en_eski_yas"])
        if s["vade_tanimli"]:
            _yaz(ws, r, 9, _lira(s["vadesi_gecmis_kurus"]), para=True)
        r += 1
    _yaz(ws, r, 1, "TOPLAM", kalin=True)
    _yaz(ws, r, 2, _lira(veri["toplam_kurus"]), kalin=True, para=True)
    for i, k in enumerate(veri["kovalar"]):
        _yaz(ws, r, 3 + i, _lira(k), kalin=True, para=True)
    for cari, avans in veri["avanslar"]:
        r += 2
        _yaz(ws, r, 1, f"Fazla ödeme (avans): {cari.unvan}")
        _yaz(ws, r, 2, _lira(avans), para=True)
    ws.freeze_panes = "B5"
    _genislik(ws, [34, 16, 14, 14, 14, 14, 14, 10, 18, 20, 30])
    return _kaydet(wb)


def yapilan_odemeler_xlsx(veri: dict) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Yapılan ödemeler"
    _yaz(ws, 1, 1, f"Yapılan Ödemeler — {veri['bas']:%d.%m.%Y} / {veri['bit']:%d.%m.%Y}", kalin=True)
    for i, b in enumerate(["Cari", "Tarih", "Ödeme şekli", "Evrak no", "Açıklama", "Tutar (₺)"], start=1):
        _yaz(ws, 3, i, b, kalin=True, doldur="DDE6F0")
    r = 4
    for g in veri["gruplar"]:
        for b in g["belgeler"]:
            _yaz(ws, r, 1, g["cari"].unvan)
            ws.cell(row=r, column=2, value=b.tarih).number_format = "DD.MM.YYYY"
            _yaz(ws, r, 3, b.get_odeme_sekli_display() or "")
            _yaz(ws, r, 4, b.evrak_no or b.harici_evrak_no)
            _yaz(ws, r, 5, b.aciklama)
            _yaz(ws, r, 6, _lira(b.tutar_kurus), para=True)
            r += 1
        _yaz(ws, r, 1, f"{g['cari'].unvan} toplamı", kalin=True)
        _yaz(ws, r, 6, _lira(g["toplam_kurus"]), kalin=True, para=True)
        r += 2
    _yaz(ws, r, 1, "GENEL TOPLAM", kalin=True)
    _yaz(ws, r, 6, _lira(veri["toplam_kurus"]), kalin=True, para=True)
    for etiket, toplam in veri["sekil_toplamlari"]:
        r += 1
        _yaz(ws, r, 5, etiket)
        _yaz(ws, r, 6, _lira(toplam), para=True)
    ws.freeze_panes = "A4"
    _genislik(ws, [34, 12, 16, 14, 36, 16])
    return _kaydet(wb)


def _kaydet(wb) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
