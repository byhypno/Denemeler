"""Ofis Kasa raporu: dönem (devir, girişler, çıkışlar, kalan), harcayan / kategori / gün kırılımı; Excel ve PDF çıktısı.

Düzen, kullanıcının 'OFİS KASA' Excel'ine benzer: solda girişler, sağda çıkışlar (fiş no ve harcayan ile),
altta TOPLAM ve KALAN. Üzerine harcayan/kategori/gün özetleri eklenmiştir. İptal edilen kayıtlar dahil değildir.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import metin
from .fields import kurus_bicimle
from .models import KasaHareketi

GIRIS, CIKIS = KasaHareketi.Yon.GIRIS, KasaHareketi.Yon.CIKIS
BELIRTILMEMIS = "Belirtilmemiş"
KATEGORISIZ = "Kategorisiz"
PARA_BICIMI = "#,##0.00"
YAZI_DIZINI = Path(settings.BASE_DIR) / "defter" / "static" / "defter" / "fonts" / "pdf"
LOGO = Path(settings.BASE_DIR) / "defter" / "static" / "defter" / "img" / "logo.png"


# ------------------------------------------------------------------ dönem seçimi
def donem_sec(hesap, istek, bugun=None):
    """(bas, bit, etiket). istek: {'donem': bu_ay|onceki_ay|son_giris|yil, 'bas':…, 'bit':…}. Varsayılan: bu ay.
    'son_giris': kasaya en son para girişinin yapıldığı günden bugüne (kullanıcının elle tuttuğu 'sayfa' mantığı)."""
    bugun = bugun or date.today()
    try:
        bas, bit = date.fromisoformat(istek.get("bas", "")), date.fromisoformat(istek.get("bit", ""))
        if bas <= bit and date(2000, 1, 1) <= bas and bit <= date(2100, 12, 31):
            return bas, bit, "Özel aralık"
    except ValueError:
        pass
    donem = istek.get("donem", "bu_ay")
    if donem == "onceki_ay":
        son = bugun.replace(day=1) - timedelta(days=1)
        return son.replace(day=1), son, "Önceki ay"
    if donem == "yil":
        return date(bugun.year, 1, 1), bugun, "Bu yıl"
    if donem == "son_giris":
        son = (hesap.hareketler.filter(iptal=False, yon=GIRIS, tarih__lte=bugun).order_by("-tarih").values_list("tarih", flat=True).first())
        if son:
            return son, bugun, "Son para girişinden bugüne"
    return bugun.replace(day=1), bugun, "Bu ay"


# ------------------------------------------------------------------ hesap
def _ad(h):
    return " ".join((h.harcayan or "").split()) or BELIRTILMEMIS


def kasa_raporu(hesap, bas: date, bit: date) -> dict:
    qs = hesap.hareketler.filter(iptal=False, tarih__gte=bas, tarih__lte=bit).select_related("kategori").order_by("tarih", "id")
    hareketler = list(qs)
    girisler = [h for h in hareketler if h.yon == GIRIS]
    cikislar = [h for h in hareketler if h.yon == CIKIS]
    devir = hesap.bakiye_kurus(tarih_kadar=bas - timedelta(days=1))
    giris_t = sum(h.tutar_kurus for h in girisler)
    cikis_t = sum(h.tutar_kurus for h in cikislar)

    kisi = defaultdict(lambda: {"ad": "", "adet": 0, "toplam": 0})
    for h in cikislar:
        anahtar = metin.katla(_ad(h))
        k = kisi[anahtar]
        k["ad"] = k["ad"] or _ad(h)
        k["adet"] += 1
        k["toplam"] += h.tutar_kurus
    kisiler = sorted(kisi.values(), key=lambda k: (k["ad"] == BELIRTILMEMIS, -k["toplam"], k["ad"]))

    kat = defaultdict(lambda: {"adet": 0, "toplam": 0})
    for h in cikislar:
        ad = h.kategori.ad if h.kategori else KATEGORISIZ
        kat[ad]["adet"] += 1
        kat[ad]["toplam"] += h.tutar_kurus
    kategoriler = [{"ad": a, **v} for a, v in sorted(kat.items(), key=lambda x: -x[1]["toplam"])]

    gun = defaultdict(lambda: [0, 0])
    for h in hareketler:
        gun[h.tarih][0 if h.yon == GIRIS else 1] += h.tutar_kurus
    gunler, bakiye = [], devir
    for t in sorted(gun):
        g, c = gun[t]
        bakiye += g - c
        gunler.append({"tarih": t, "giris": g, "cikis": c, "bakiye": bakiye})

    fissiz = [h for h in cikislar if not h.makbuz_no.strip()]
    return {
        "hesap": hesap, "bas": bas, "bit": bit,
        "devir": devir, "giris_toplam": giris_t, "cikis_toplam": cikis_t, "kalan": devir + giris_t - cikis_t,
        "girisler": girisler, "cikislar": cikislar,
        "kisiler": kisiler, "kategoriler": kategoriler, "gunler": gunler,
        "en_buyuk": sorted(cikislar, key=lambda h: (-h.tutar_kurus, h.tarih))[:10],
        "fissiz_adet": len(fissiz), "fissiz_toplam": sum(h.tutar_kurus for h in fissiz),
        "ortalama_gunluk_cikis": (cikis_t // max((bit - bas).days + 1, 1)),
    }


def dosya_adi(r, uzanti):
    return f"ofis_kasa_{r['bas']:%Y%m%d}_{r['bit']:%Y%m%d}.{uzanti}"


# ------------------------------------------------------------------ Excel
_KALIN = Font(bold=True)
_BASLIK_DOLGU = PatternFill("solid", fgColor="E3ECF4")
_TOPLAM_DOLGU = PatternFill("solid", fgColor="F1F5F9")
_INCE = Side(style="thin", color="C5CED8")
_CERCEVE = Border(left=_INCE, right=_INCE, top=_INCE, bottom=_INCE)


def _lira(kurus):
    return Decimal(int(kurus)) / 100


def _yaz(ws, satir, sutun, deger, kalin=False, para=False, dolgu=None, cerceve=False, hiza=None):
    if isinstance(deger, str):
        deger = ILLEGAL_CHARACTERS_RE.sub("", deger)   # \x0b gibi denetim karakterleri Excel dosyasını bozar
    h = ws.cell(row=satir, column=sutun, value=deger)
    if isinstance(deger, str):
        h.data_type = "s"          # '=' ile başlayan metin formüle dönüşmesin
    if kalin:
        h.font = _KALIN
    if para:
        h.number_format = PARA_BICIMI
        h.alignment = Alignment(horizontal="right")
    if hiza:
        h.alignment = Alignment(horizontal=hiza, vertical="top", wrap_text=(hiza == "left"))
    if dolgu:
        h.fill = dolgu
    if cerceve:
        h.border = _CERCEVE
    return h


def _genislik(ws, olculer):
    for i, g in enumerate(olculer, start=1):
        ws.column_dimensions[get_column_letter(i)].width = g


def _tarih(ws, satir, sutun, d, cerceve=True):
    h = _yaz(ws, satir, sutun, d, cerceve=cerceve, hiza="center")
    h.number_format = "DD.MM.YYYY"


def rapor_xlsx(r) -> bytes:
    wb = Workbook()
    _sayfa_defter(wb.active, r)
    _sayfa_ozet(wb.create_sheet("Özet"), r)
    _sayfa_gunluk(wb.create_sheet("Günlük"), r)
    cikti = BytesIO()
    wb.save(cikti)
    return cikti.getvalue()


def _sayfa_defter(ws, r):
    """Kullanıcının sayfası gibi: sol girişler, sağ çıkışlar."""
    ws.title = "Kasa defteri"
    _yaz(ws, 1, 1, f"{r['hesap'].ad} · {r['bas']:%d.%m.%Y} – {r['bit']:%d.%m.%Y}", kalin=True)
    ws["A1"].font = Font(bold=True, size=14)
    ws.row_dimensions[1].height = 22
    ust = 3
    for i, b in enumerate(("Tarih", "Açıklama", "Tutar"), start=1):
        _yaz(ws, ust, i, b, kalin=True, dolgu=_BASLIK_DOLGU, cerceve=True, hiza="center")
    for i, b in enumerate(("Tarih", "Açıklama", "Fiş no", "Harcayan", "Tutar"), start=5):
        _yaz(ws, ust, i, b, kalin=True, dolgu=_BASLIK_DOLGU, cerceve=True, hiza="center")
    _yaz(ws, ust - 1, 1, "PARA GİRİŞLERİ", kalin=True)
    _yaz(ws, ust - 1, 5, "PARA ÇIKIŞLARI", kalin=True)

    satir = ust + 1
    devir_satiri = satir
    _tarih(ws, satir, 1, r["bas"])
    _yaz(ws, satir, 2, "DEVİR", kalin=True, cerceve=True)
    _yaz(ws, satir, 3, _lira(r["devir"]), para=True, cerceve=True)
    sol = satir + 1
    for h in r["girisler"]:
        _tarih(ws, sol, 1, h.tarih)
        _yaz(ws, sol, 2, h.aciklama or "PARA GİRİŞİ", cerceve=True, hiza="left")
        _yaz(ws, sol, 3, _lira(h.tutar_kurus), para=True, cerceve=True)
        sol += 1
    sag = ust + 1
    for h in r["cikislar"]:
        _tarih(ws, sag, 5, h.tarih)
        _yaz(ws, sag, 6, h.aciklama, cerceve=True, hiza="left")
        _yaz(ws, sag, 7, h.makbuz_no, cerceve=True, hiza="center")
        _yaz(ws, sag, 8, _ad(h) if h.harcayan else "", cerceve=True, hiza="center")
        _yaz(ws, sag, 9, _lira(h.tutar_kurus), para=True, cerceve=True)
        sag += 1

    son = max(sol, sag) + 1
    for sutunlar, etiket_sutun, tutar_sutun, tutar in (
            (range(1, 4), 2, 3, r["devir"] + r["giris_toplam"]), (range(5, 10), 8, 9, r["cikis_toplam"])):
        for s in sutunlar:
            _yaz(ws, son, s, None, dolgu=_TOPLAM_DOLGU, cerceve=True)
        _yaz(ws, son, etiket_sutun, "TOPLAM", kalin=True, dolgu=_TOPLAM_DOLGU, cerceve=True, hiza="center")
        _yaz(ws, son, tutar_sutun, _lira(tutar), kalin=True, para=True, dolgu=_TOPLAM_DOLGU, cerceve=True)
    _yaz(ws, son + 2, 8, "KALAN", kalin=True, dolgu=_BASLIK_DOLGU, cerceve=True, hiza="center")
    k = _yaz(ws, son + 2, 9, _lira(r["kalan"]), kalin=True, para=True, dolgu=_BASLIK_DOLGU, cerceve=True)
    k.font = Font(bold=True, size=12)
    _yaz(ws, son + 3, 2, f"Devir + girişler − çıkışlar = kalan. Fişi girilmemiş çıkış: {r['fissiz_adet']} adet "
                         f"({kurus_bicimle(r['fissiz_toplam'])} ₺). İptal edilen kayıtlar dahil değildir.")
    _genislik(ws, [12, 36, 14, 3, 12, 44, 10, 16, 14])
    ws.freeze_panes = ws.cell(row=ust + 1, column=1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{ust}:{ust}"
    return devir_satiri


def _tablo(ws, satir, baslik, basliklar, satirlar, toplam=None):
    """Küçük bir özet tablosu yazar; sonraki boş satırı döner. satirlar: [(metin, ..., kurus)] — son sütun para."""
    _yaz(ws, satir, 1, baslik, kalin=True)
    ws.cell(row=satir, column=1).font = Font(bold=True, size=12)
    satir += 1
    for i, b in enumerate(basliklar, start=1):
        _yaz(ws, satir, i, b, kalin=True, dolgu=_BASLIK_DOLGU, cerceve=True, hiza="center")
    satir += 1
    for s in satirlar:
        for i, v in enumerate(s, start=1):
            if i == len(s):
                _yaz(ws, satir, i, _lira(v), para=True, cerceve=True)
            elif isinstance(v, int):
                _yaz(ws, satir, i, v, cerceve=True, hiza="center")
            else:
                _yaz(ws, satir, i, v, cerceve=True, hiza="left")
        satir += 1
    if toplam is not None:
        for i in range(1, len(basliklar) + 1):
            _yaz(ws, satir, i, None, dolgu=_TOPLAM_DOLGU, cerceve=True)
        _yaz(ws, satir, 1, "TOPLAM", kalin=True, dolgu=_TOPLAM_DOLGU, cerceve=True)
        _yaz(ws, satir, len(basliklar), _lira(toplam), kalin=True, para=True, dolgu=_TOPLAM_DOLGU, cerceve=True)
        satir += 1
    return satir + 1


def _sayfa_ozet(ws, r):
    _yaz(ws, 1, 1, f"{r['hesap'].ad} özeti · {r['bas']:%d.%m.%Y} – {r['bit']:%d.%m.%Y}").font = Font(bold=True, size=14)
    satir = _tablo(ws, 3, "Kasa durumu", ("Kalem", "Tutar"), [
        ("Devir (dönem başı bakiye)", r["devir"]), ("Para girişleri", r["giris_toplam"]),
        ("Para çıkışları", r["cikis_toplam"]), ("KALAN", r["kalan"]),
        ("Günlük ortalama çıkış", r["ortalama_gunluk_cikis"])])
    satir = _tablo(ws, satir, "Kişi bazında harcama (harcayan)", ("Harcayan", "Adet", "Tutar"),
                   [(k["ad"], k["adet"], k["toplam"]) for k in r["kisiler"]], toplam=r["cikis_toplam"])
    satir = _tablo(ws, satir, "Kategori bazında harcama", ("Kategori", "Adet", "Tutar"),
                   [(k["ad"], k["adet"], k["toplam"]) for k in r["kategoriler"]], toplam=r["cikis_toplam"])
    satir = _tablo(ws, satir, "En büyük 10 çıkış", ("Tarih", "Açıklama", "Harcayan", "Tutar"),
                   [(f"{h.tarih:%d.%m.%Y}", h.aciklama, _ad(h) if h.harcayan else "", h.tutar_kurus) for h in r["en_buyuk"]])
    _yaz(ws, satir, 1, f"Fişi (makbuz no) girilmemiş çıkış: {r['fissiz_adet']} adet, {kurus_bicimle(r['fissiz_toplam'])} ₺")
    _genislik(ws, [34, 40, 18, 16])


def _sayfa_gunluk(ws, r):
    _yaz(ws, 1, 1, "Gün gün hareket").font = Font(bold=True, size=14)
    for i, b in enumerate(("Tarih", "Giriş", "Çıkış", "Gün sonu bakiye"), start=1):
        _yaz(ws, 3, i, b, kalin=True, dolgu=_BASLIK_DOLGU, cerceve=True, hiza="center")
    satir = 4
    for g in r["gunler"]:
        _tarih(ws, satir, 1, g["tarih"])
        for i, anahtar in enumerate(("giris", "cikis", "bakiye"), start=2):
            _yaz(ws, satir, i, _lira(g[anahtar]), para=True, cerceve=True)
        satir += 1
    _genislik(ws, [14, 16, 16, 18])
    ws.freeze_panes = "A4"


# ------------------------------------------------------------------ PDF
def _yazi_tipleri():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping
    if "PJS-Regular" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("PJS-Regular", str(YAZI_DIZINI / "PlusJakartaSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("PJS-Bold", str(YAZI_DIZINI / "PlusJakartaSans-Bold.ttf")))
        addMapping("PJS", 0, 0, "PJS-Regular")
        addMapping("PJS", 1, 0, "PJS-Bold")
        addMapping("PJS", 0, 1, "PJS-Regular")
        addMapping("PJS", 1, 1, "PJS-Bold")
    return "PJS-Regular", "PJS-Bold"


def rapor_pdf(r) -> bytes:
    """Dik A4, dar kenar boşluğu. Mümkünse TEK sayfaya sığdırır: yazı boyutunu kademeli küçültür (en küçük 5,5 pt);
    yine sığmazsa en küçük boyutta birden çok sayfa üretir."""
    son = None
    for fs in (8.5, 8, 7.5, 7, 6.5, 6, 5.5):
        pdf, sayfa = _pdf_uret(r, fs)
        son = pdf
        if sayfa == 1:
            break
    return son


def _pdf_uret(r, fs):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    normal, kalin = _yazi_tipleri()
    mavi, acik, cizgi = colors.HexColor("#1F4E79"), colors.HexColor("#E3ECF4"), colors.HexColor("#C5CED8")
    lead = fs * 1.22
    pad = max(1.2, fs * 0.28)
    s_n = ParagraphStyle("n", fontName=normal, fontSize=fs, leading=lead)
    s_k = ParagraphStyle("k", parent=s_n, fontName=kalin)
    s_h2 = ParagraphStyle("h2", fontName=kalin, fontSize=fs + 2, leading=fs + 4, textColor=mavi, spaceBefore=fs * 0.7, spaceAfter=2)
    s_h1 = ParagraphStyle("h1", fontName=kalin, fontSize=fs + 8, leading=fs + 11, textColor=mavi)
    s_not = ParagraphStyle("not", parent=s_n, textColor=colors.HexColor("#5B6877"), fontSize=max(fs - 1, 5), leading=lead)

    def tl(kurus):
        return kurus_bicimle(kurus) + " ₺"

    def p(metin_, stil=s_n):
        return Paragraph(str(metin_).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), stil)

    from reportlab.pdfbase.pdfmetrics import stringWidth

    def en(metinler, kalin_=False):
        """Sütunun içeriğine göre genişlik (pt): en uzun metin + iç boşluk."""
        return max(stringWidth(str(m), kalin if kalin_ else normal, fs) for m in metinler) + 9

    tarih_w = en(["00.00.0000"])

    def tablo(veri, genislik, sayi_sutunlari=(), toplam_satiri=False):
        t = Table(veri, colWidths=genislik, repeatRows=1, hAlign="LEFT")
        stil = [("FONT", (0, 0), (-1, -1), normal, fs), ("FONT", (0, 0), (-1, 0), kalin, fs),
                ("BACKGROUND", (0, 0), (-1, 0), acik), ("GRID", (0, 0), (-1, -1), 0.3, cizgi),
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        for c in sayi_sutunlari:
            stil.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
        if toplam_satiri:
            stil += [("FONT", (0, -1), (-1, -1), kalin, fs), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9"))]
        t.setStyle(TableStyle(stil))
        return t

    cikti = BytesIO()
    kenar = 7 * mm
    sayfa = A4
    genis = sayfa[0] - 2 * kenar
    dok = SimpleDocTemplate(cikti, pagesize=sayfa, leftMargin=kenar, rightMargin=kenar, topMargin=kenar, bottomMargin=kenar + 3 * mm,
                            title=f"{r['hesap'].ad} raporu", author="Egeser Cari")

    def alt_bilgi(tuval, doc):
        tuval.saveState()
        tuval.setFont(normal, 6.5)
        tuval.setFillColor(colors.HexColor("#5B6877"))
        tuval.drawString(kenar, 4.5 * mm, f"{r['hesap'].ad} · {r['bas']:%d.%m.%Y} – {r['bit']:%d.%m.%Y} · Hazırlanma: {date.today():%d.%m.%Y}")
        tuval.drawRightString(sayfa[0] - kenar, 4.5 * mm, f"Sayfa {doc.page}")
        tuval.restoreState()

    ogeler = []
    logo = Image(str(LOGO), width=24 * mm, height=12 * mm, kind="proportional") if LOGO.exists() else ""
    bt = Table([[logo, [p(f"{r['hesap'].ad} raporu", s_h1), p(f"{r['bas']:%d.%m.%Y} – {r['bit']:%d.%m.%Y}", s_n)]]],
               colWidths=[28 * mm, genis - 28 * mm])
    bt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    ogeler += [bt, Spacer(1, 4)]

    kpi_veri = [[p("Devir", s_not), p("Para girişleri", s_not), p("Para çıkışları", s_not), p("KALAN", s_not)],
                [p(tl(r["devir"]), s_k), p(tl(r["giris_toplam"]), s_k), p(tl(r["cikis_toplam"]), s_k),
                 p(tl(r["kalan"]), ParagraphStyle("kal", parent=s_k, fontSize=fs + 3, leading=fs + 5, textColor=mavi))]]
    kt = Table(kpi_veri, colWidths=[genis / 4] * 4)
    kt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, cizgi), ("INNERGRID", (0, 0), (-1, -1), 0.3, cizgi),
                            ("BACKGROUND", (0, 0), (-1, 0), acik), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    ogeler += [kt, Spacer(1, 2),
               p(f"Devir + girişler − çıkışlar = kalan. Günlük ortalama çıkış {tl(r['ortalama_gunluk_cikis'])}. "
                 f"Fişi girilmemiş çıkış: {r['fissiz_adet']} adet ({tl(r['fissiz_toplam'])}). İptal edilen kayıtlar dahil değildir.", s_not)]

    # Girişler (sol) + kişi bazında harcama (sağ) yan yana: dikey yer kazanır
    yarim = genis / 2 - 1.5 * mm
    giris = [["Tarih", "Açıklama", "Tutar"], [f"{r['bas']:%d.%m.%Y}", p("DEVİR", s_k), tl(r["devir"])]]
    giris += [[f"{h.tarih:%d.%m.%Y}", p(h.aciklama or "PARA GİRİŞİ"), tl(h.tutar_kurus)] for h in r["girisler"]]
    giris.append(["", "TOPLAM", tl(r["devir"] + r["giris_toplam"])])
    g_tutar = en([tl(r["devir"] + r["giris_toplam"])] + [tl(h.tutar_kurus) for h in r["girisler"]], True)
    g_kol = [tarih_w, yarim - tarih_w - g_tutar, g_tutar]
    kisi = [["Harcayan", "Adet", "Tutar", "Pay"]] + [
        [p(k["ad"]), str(k["adet"]), tl(k["toplam"]), f"%{round(k['toplam'] * 100 / r['cikis_toplam'])}" if r["cikis_toplam"] else ""]
        for k in r["kisiler"]] + [["TOPLAM", "", tl(r["cikis_toplam"]), ""]]
    k_tutar = en([tl(k["toplam"]) for k in r["kisiler"]] + [tl(r["cikis_toplam"])], True)
    k_kol = [0, en(["Adet", "999"]), k_tutar, en(["%100"])]
    k_kol[0] = yarim - sum(k_kol[1:])
    ust = Table([[[p("Para girişleri", s_h2), tablo(giris, g_kol, (2,), True)],
                  [p("Kişi bazında harcama (harcayan)", s_h2), tablo(kisi, k_kol, (1, 2, 3), True)]]], colWidths=[genis / 2, genis / 2])
    ust.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 1.5 * mm),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    ogeler.append(ust)

    # Çıkışlar: kategori sütunu yalnızca kullanılıyorsa
    kategorili = any(h.kategori for h in r["cikislar"])
    baslik = ["Tarih", "Açıklama", "Fiş no", "Harcayan"] + (["Kategori"] if kategorili else []) + ["Tutar"]
    veri = [baslik]
    for h in r["cikislar"]:
        satir = [f"{h.tarih:%d.%m.%Y}", p(h.aciklama), p(h.makbuz_no), p(_ad(h) if h.harcayan else "")]
        if kategorili:
            satir.append(p(h.kategori.ad if h.kategori else ""))
        veri.append(satir + [tl(h.tutar_kurus)])
    if not r["cikislar"]:
        veri.append(["", p("Bu dönemde çıkış yok.")] + [""] * (len(baslik) - 2))
    veri.append(["", "TOPLAM"] + [""] * (len(baslik) - 3) + [tl(r["cikis_toplam"])])
    c_tutar = en([tl(h.tutar_kurus) for h in r["cikislar"]] + [tl(r["cikis_toplam"])], True)
    c_fis = min(max(en([h.makbuz_no for h in r["cikislar"]] + ["Fiş no"]), en(["Fiş no"])), 70)
    c_kisi = min(en([_ad(h) for h in r["cikislar"] if h.harcayan] + ["Harcayan"]), 110)
    c_kat = min(en([h.kategori.ad for h in r["cikislar"] if h.kategori] + ["Kategori"]), 90) if kategorili else 0
    kolonlar = [tarih_w, genis - tarih_w - c_fis - c_kisi - c_kat - c_tutar, c_fis, c_kisi] + ([c_kat] if kategorili else []) + [c_tutar]
    ogeler += [p("Para çıkışları", s_h2), tablo(veri, kolonlar, (len(baslik) - 1,), True)]

    # Kategori özeti: yalnızca kategori kullanılıyorsa
    if kategorili:
        kat = [["Kategori", "Adet", "Tutar", "Pay"]] + [
            [p(k["ad"]), str(k["adet"]), tl(k["toplam"]), f"%{round(k['toplam'] * 100 / r['cikis_toplam'])}" if r["cikis_toplam"] else ""]
            for k in r["kategoriler"]] + [["TOPLAM", "", tl(r["cikis_toplam"]), ""]]
        kk = [0, en(["Adet", "999"]), en([tl(k["toplam"]) for k in r["kategoriler"]] + [tl(r["cikis_toplam"])], True), en(["%100"])]
        kk[0] = yarim - sum(kk[1:])
        ogeler += [p("Kategori bazında harcama", s_h2), tablo(kat, kk, (1, 2, 3), True)]

    dok.build(ogeler, onFirstPage=alt_bilgi, onLaterPages=alt_bilgi)
    return cikti.getvalue(), dok.page
