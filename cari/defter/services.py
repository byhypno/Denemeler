from django.db.models import Case, F, IntegerField, Sum, When

from .models import Belge


def _etkili_toplam():
    return Sum(
        Case(
            When(tur__in=Belge.ARTIRAN, then=F("tutar_kurus")),
            When(tur__in=Belge.AZALTAN, then=-F("tutar_kurus")),
            default=0,
            output_field=IntegerField(),
        )
    )


def bakiye_kurus(cari, tarih_kadar=None) -> int:
    """Cari borç bakiyesi (kuruş). Pozitif = tedarikçiye borçluyuz. İptal kayıtlar sayılmaz."""
    qs = Belge.objects.filter(cari=cari, iptal=False)
    if tarih_kadar:
        qs = qs.filter(tarih__lte=tarih_kadar)
    return qs.aggregate(t=_etkili_toplam())["t"] or 0


def ekstre(cari, baslangic=None, bitis=None):
    """Satır satır ekstre: (belge, bakiye_kurus) listesi + dönem başı bakiye."""
    onceki = 0
    if baslangic:
        qs0 = Belge.objects.filter(cari=cari, iptal=False, tarih__lt=baslangic)
        onceki = qs0.aggregate(t=_etkili_toplam())["t"] or 0
    qs = Belge.objects.filter(cari=cari, iptal=False)
    if baslangic:
        qs = qs.filter(tarih__gte=baslangic)
    if bitis:
        qs = qs.filter(tarih__lte=bitis)
    satirlar, bakiye = [], onceki
    for b in qs.order_by("tarih", "id"):
        bakiye += b.etki * b.tutar_kurus
        satirlar.append((b, bakiye))
    return onceki, satirlar
