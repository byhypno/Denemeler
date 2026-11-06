"""Para alanı: tutarlar VERİTABANINDA tamsayı kuruş olarak saklanır (float yok).

Arayüzde Türk biçimi kullanılır: 1.234,50
Belirsiz girişler (ör. 1234.50) kasten reddedilir: yanlışlıkla 123.450 TL olmasın.
"""
import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

_TR_TUTAR = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+)(,\d{1,2})?$")


def kurus_bicimle(kurus) -> str:
    """123450 -> '1.234,50'"""
    if kurus is None:
        return ""
    negatif = kurus < 0
    lira, kr = divmod(abs(int(kurus)), 100)
    metin = f"{lira:,}".replace(",", ".") + f",{kr:02d}"
    return "-" + metin if negatif else metin


def tl_ayristir(metin: str) -> int:
    """'1.234,50' -> 123450. Geçersizse ValueError."""
    m = metin.strip().replace("₺", "").replace(" ", "").replace(" ", "")
    if not _TR_TUTAR.match(m):
        raise ValueError(metin)
    negatif = m.startswith("-")
    tam, _, kesir = m.lstrip("-").partition(",")
    kurus = int(tam.replace(".", "")) * 100 + int((kesir + "00")[:2])
    return -kurus if negatif else kurus


class KurusFormField(forms.CharField):
    default_error_messages = {"invalid": "Tutarı 1.234,50 biçiminde girin."}

    def to_python(self, value):
        value = super().to_python(value)
        if value in (None, ""):
            return None
        try:
            return tl_ayristir(value)
        except ValueError:
            raise ValidationError(self.error_messages["invalid"], code="invalid")

    def prepare_value(self, value):
        return kurus_bicimle(value) if isinstance(value, int) else value

    def has_changed(self, initial, data):
        if self.disabled:
            return False
        try:
            return self.to_python(data) != initial
        except ValidationError:
            return True


class KurusField(models.BigIntegerField):
    """Kuruş cinsinden tamsayı; formda TL olarak gösterilir."""

    description = "Kuruş cinsinden tutar"

    def formfield(self, **kwargs):
        # BigIntegerField'ın min/max parametrelerini atlayıp doğrudan kendi alanımızı kullan.
        return models.Field.formfield(self, **{"form_class": KurusFormField, **kwargs})
