from django import template

from ..fields import kurus_bicimle

register = template.Library()


@register.filter
def kurus_tl(deger):
    """123450 -> '1.234,50 ₺'"""
    if deger in (None, ""):
        return "—"
    return f"{kurus_bicimle(int(deger))} ₺"


@register.filter
def kurus_say(deger):
    """123450 -> '1.234,50' (simgesiz)"""
    if deger in (None, ""):
        return "—"
    return kurus_bicimle(int(deger))


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
