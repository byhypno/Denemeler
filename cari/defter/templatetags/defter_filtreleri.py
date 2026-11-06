import zlib

from django import template
from django.utils.html import format_html

from .. import trend
from ..fields import kurus_bicimle

register = template.Library()


def _tutar(metin, kurus):
    """Eksi tutarlar kırmızı (renge ek olarak '-' işareti de durur: yalnızca renge güvenilmez)."""
    return format_html('<span class="eksi">{}</span>', metin) if kurus < 0 else metin


@register.filter
def kurus_tl(deger):
    """123450 -> '1.234,50 ₺'"""
    if deger in (None, ""):
        return "—"
    return _tutar(f"{kurus_bicimle(int(deger))} ₺", int(deger))


@register.filter
def kurus_ham(deger):
    """123450 -> '1.234,50' (düz metin; form alanı değeri için, işaretleme yok)"""
    return kurus_bicimle(int(deger)) if deger not in (None, "") else ""


@register.filter
def kurus_say(deger):
    """123450 -> '1.234,50' (simgesiz)"""
    if deger in (None, ""):
        return "—"
    return _tutar(kurus_bicimle(int(deger)), int(deger))


@register.simple_tag
def ikon(ad, sinif=""):
    """Sprite'tan SVG simgesi: {% ikon "kasa" %}. Dekoratiftir (ekran okuyucudan gizli); anlamı yanındaki metin taşır."""
    return format_html('<svg class="ikon {}" aria-hidden="true" focusable="false"><use href="#i-{}"/></svg>', sinif, ad)


@register.filter
def sozluk_al(sozluk, anahtar):
    """{{ sozluk|sozluk_al:anahtar }} — şablonda sözlükten değer okur."""
    try:
        return sozluk.get(anahtar)
    except AttributeError:
        return None


@register.filter
def boyut(bayt):
    """1234567 -> '1,2 MB'"""
    try:
        b = float(bayt)
    except (TypeError, ValueError):
        return "—"
    for birim in ("bayt", "KB", "MB", "GB"):
        if b < 1024 or birim == "GB":
            return (f"{int(b)} {birim}" if birim == "bayt" else f"{b:.1f} {birim}".replace(".", ","))
        b /= 1024


@register.filter
def ek_etiketi(sahip):
    from ..ek_views import sahip_etiketi
    return sahip_etiketi(sahip)


_TR_BUYUK = str.maketrans({"i": "İ", "ı": "I"})


def bas_harfler(ad) -> str:
    """'Eröz Hırdavat Ltd.' -> 'EH'; tek sözcükte ilk iki harf. Türkçe büyük harf kuralı (i->İ)."""
    sozcukler = [s for s in str(ad or "").replace(".", " ").split() if s[:1].isalnum()]
    if not sozcukler:
        return "?"
    harf = sozcukler[0][0] + sozcukler[1][0] if len(sozcukler) > 1 else sozcukler[0][:2]
    return harf.translate(_TR_BUYUK).upper()


@register.simple_tag
def avatar(ad, boyut=""):
    """Baş harfli yuvarlak simge; renk addan türetilir (aynı ad her zaman aynı renk)."""
    renk = zlib.crc32(str(ad or "").encode("utf-8")) % 8 + 1
    return format_html('<span class="avatar av-{} {}" aria-hidden="true">{}</span>', renk, boyut, bas_harfler(ad))


@register.simple_tag
def sparkline(seri):
    """Aylık seriden satır içi mini grafik (dekoratif; değer kartta yazılı)."""
    yollar = trend.sparkline_yollari(list(seri))
    if not yollar:
        return ""
    return format_html('<svg class="sparkline" viewBox="0 0 92 32" aria-hidden="true" focusable="false">'
                       '<path class="alan" d="{}"/><path class="cizgi" d="{}"/></svg>', yollar[1], yollar[0])


@register.simple_tag
def degisim_etiketi(d, ton="notr"):
    """trend.degisim sonucu -> 'önceki aya göre' etiketi. ton: 'yuksek_iyi' | 'yuksek_kotu' | 'notr'.
    Renk yalnızca yardımcı sinyaldir; yön oku + yüzde + gizli metin her zaman yazılıdır."""
    if not d:
        return ""
    sinif = ""
    if d["yon"] != "yatay" and ton != "notr":
        iyi = (d["yon"] == "yukari") == (ton == "yuksek_iyi")
        sinif = "iyi" if iyi else "kotu"
    ok = {"yukari": "ok-yukari", "asagi": "ok-asagi"}.get(d["yon"], "")
    yuzde = f"%{d['yuzde']}" if d["yuzde"] is not None else ""
    ad = {"yukari": "artış", "asagi": "azalış", "yatay": "değişim yok"}[d["yon"]]
    ikon_html = ikon(ok, "kucuk") if ok else ""
    return format_html('<span class="degisim {}">{}{}<span class="sr-only">{} {}, önceki aya göre</span></span>',
                       sinif, ikon_html, yuzde or ("—" if not ok else ""), yuzde.replace("%", "yüzde ") if yuzde else "", ad)


@register.filter
def cevir_pozitif(deger):
    """-5 -> 5 (gecikme gününü '5 gün gecikti' diye yazmak için)"""
    try:
        return abs(int(deger))
    except (TypeError, ValueError):
        return deger


@register.filter
def miktar(deger):
    """Decimal('1250.500') -> '1.250,5' ; tam sayı: '3'"""
    try:
        d = deger.normalize()
    except AttributeError:
        return deger
    tam, _, kesir = f"{d:f}".partition(".")
    tam = f"{int(tam):,}".replace(",", ".")
    return f"{tam},{kesir}" if kesir else tam


@register.filter
def birim_tl(deger):
    """Birim fiyat (KURUŞ, Decimal) -> '1.234,50 ₺'; kuruşun altı varsa 4 haneye kadar ('1,005 ₺')."""
    if deger in (None, ""):
        return "—"
    from decimal import Decimal
    lira = Decimal(deger) / 100
    metin = f"{lira:,.4f}".replace(",", "_").replace(".", ",").replace("_", ".")
    tam, _, kesir = metin.partition(",")
    kesir = kesir.rstrip("0").ljust(2, "0")
    return f"{tam},{kesir} ₺"


@register.simple_tag
def fiyat_degisim(d):
    """Malzeme fiyat değişimi etiketi: artış KÖTÜ (kırmızı), azalış iyi (yeşil). Renge ek olarak ok + yüzde + gizli metin vardır."""
    if not d:
        return ""
    yuzde = f"{d['yuzde']}".replace(".", ",")
    if d["yon"] == "yatay":
        return format_html('<span class="degisim">{}<span class="sr-only">fiyat değişmedi</span></span>', "—")
    kotu = d["yon"] == "yukari"
    ad = "zam" if kotu else "indirim"
    return format_html('<span class="degisim {}">{}%{}<span class="sr-only"> {}</span></span>',
                       "kotu" if kotu else "iyi", ikon("ok-yukari" if kotu else "ok-asagi", "kucuk"), yuzde, ad)


@register.filter
def cevir_virgul(deger):
    """'12.5' -> '12,5' (ondalık ayırıcı virgül)"""
    return str(deger).replace(".", ",")
