from django import template
from django.utils.html import format_html

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
