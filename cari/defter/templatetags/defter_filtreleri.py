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
