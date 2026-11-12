"""Para alanı: tutarlar VERİTABANINDA tamsayı kuruş olarak saklanır (float yok).

Arayüzde Türk biçimi kullanılır: 1.234,50
Belirsiz girişler (ör. 1234.50) kasten reddedilir: yanlışlıkla 123.450 TL olmasın.
"""
import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

MAKS_KURUS = 10**13          # 100 milyar TL: bunun üstü yazım hatasıdır ve SQLite SUM() tamsayı taşmasına yol açar

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
    if kurus > MAKS_KURUS:
        raise ValueError(metin)
    return -kurus if negatif else kurus


_TR_ONDALIK = re.compile(r"^(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$")


def ondalik_ayristir(metin: str, en_cok: int = 4) -> Decimal:
    """'1.250,5' -> Decimal('1250.5'). Miktar/birim fiyat için. Nokta yalnızca binlik ayırıcıdır (1.5 gibi belirsiz giriş reddedilir).
    Geçersizse ValueError."""
    m = metin.strip().replace(" ", "")
    if not _TR_ONDALIK.match(m):
        raise ValueError(metin)
    tam, _, kesir = m.partition(",")
    if len(kesir) > en_cok:
        raise ValueError(metin)
    return Decimal(tam.replace(".", "") + "." + (kesir or "0"))


class KurusFormField(forms.CharField):
    default_error_messages = {"invalid": "Tutarı 1.234,50 biçiminde girin (en çok 100.000.000.000 ₺)."}

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
    default_validators = [MaxValueValidator(MAKS_KURUS), MinValueValidator(-MAKS_KURUS)]    # yönetim paneli/doğrudan modelde de üst sınır

    def formfield(self, **kwargs):
        # BigIntegerField'ın min/max parametrelerini atlayıp doğrudan kendi alanımızı kullan.
        return models.Field.formfield(self, **{"form_class": KurusFormField, **kwargs})
