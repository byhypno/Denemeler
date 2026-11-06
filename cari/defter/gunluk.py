"""İşlem günlüğü: kayıt ekleme/değiştirme/silme, giriş/çıkış ve özel olaylar.

Kural: günlüğe yazılmayan değişiklik YOKTUR. Bu yüzden uygulama kodunda izlenen modellerde toplu
`queryset.update()` kullanılmaz (sinyal göndermez); gerekiyorsa `gunluk.yaz()` ile açıkça kaydedilir.
Bunu `test_gunluk.test_update_koruma_testi` denetler.
"""
import contextvars
from contextlib import contextmanager

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save

from .fields import KurusField, kurus_bicimle

_kullanici = contextvars.ContextVar("gunluk_kullanici", default="sistem")
_sessiz = contextvars.ContextVar("gunluk_sessiz", default=False)

HARIC_ALANLAR = {"id", "olusturma", "guncelleme", "yuklenme"}     # otomatik zaman damgaları
GIZLI_ALANLAR = {"password"}                                       # değeri asla yazılmaz
SOYUT_IPTAL = ("iptal", "kaldirildi")


def kullanici_adi() -> str:
    return _kullanici.get()


@contextmanager
def kullanici_olarak(ad):
    token = _kullanici.set(ad or "anonim")
    try:
        yield
    finally:
        _kullanici.reset(token)


@contextmanager
def sessiz(ozet: str = ""):
    """
    İçerideki tek tek kayıt değişiklikleri yazılmaz; blok istisnasız biterse TEK bir özet kaydı yazılır.
    `with sessiz("...") as g:` ile dönen sözlükteki g["metin"] bloğun sonunda güncellenebilir.
    """
    g = {"metin": ozet}
    token = _sessiz.set(True)
    try:
        yield g
    finally:
        _sessiz.reset(token)
    yaz("OZEL", model="Toplu işlem", ayrinti=g["metin"])


def yaz(islem, model="", nesne=None, degisiklik=None, ayrinti="", kullanici=None):
    from .models import IslemGunlugu
    return IslemGunlugu.objects.create(
        kullanici=(kullanici or kullanici_adi())[:150], islem=islem, model=model[:60],
        nesne_id=getattr(nesne, "pk", None), nesne_ozeti=(str(nesne)[:300] if nesne is not None else ""),
        degisiklik=degisiklik or {}, ayrinti=ayrinti)


# ------------------------------------------------------------------ değer gösterimi
def _goster(alan, nesne):
    """Bir alanın okunur değeri (para: 1.234,50 ₺, ilişki: kaydın adı, boolean: Evet/Hayır)."""
    deger = getattr(nesne, alan.attname)
    if alan.name in GIZLI_ALANLAR:
        return "***"
    if deger is None or deger == "":
        return None
    if isinstance(alan, KurusField):
        return f"{kurus_bicimle(deger)} ₺"
    if isinstance(alan, models.ForeignKey):
        try:
            return str(getattr(nesne, alan.name))
        except Exception:
            return f"#{deger}"
    if isinstance(alan, models.BooleanField):
        return "Evet" if deger else "Hayır"
    if alan.choices:
        return str(dict(alan.flatchoices).get(deger, deger))
    if isinstance(deger, (int, float)):
        return deger
    return str(deger)


def _alanlar(model):
    return [a for a in model._meta.concrete_fields if a.name not in HARIC_ALANLAR]


def _etiket(alan):
    ad = str(alan.verbose_name)
    return ad[:1].upper() + ad[1:]            # capitalize() iç büyük harfleri küçültürdü (KDV -> Kdv)


MODEL_ADI = {"User": "Kullanıcı"}


def _model_adi(sender):
    return MODEL_ADI.get(sender.__name__, sender.__name__)


# ------------------------------------------------------------------ sinyaller
def _kayit_oncesi(sender, instance, raw=False, **kw):
    instance._gunluk_eski = None
    if raw or _sessiz.get() or instance.pk is None:
        return
    instance._gunluk_eski = sender._default_manager.filter(pk=instance.pk).first()


def _kayit_sonrasi(sender, instance, created, raw=False, **kw):
    if raw or _sessiz.get():
        return
    ad = _model_adi(sender)
    if created:
        degisiklik = {}
        for a in _alanlar(sender):
            v = _goster(a, instance)
            if v is not None and v is not False and v != "Hayır":
                degisiklik[_etiket(a)] = [None, v]
        yaz("OLUSTURDU", ad, instance, degisiklik)
        return
    eski = getattr(instance, "_gunluk_eski", None)
    if eski is None:
        return
    degisiklik, iptal_oldu = {}, False
    for a in _alanlar(sender):
        if getattr(eski, a.attname) != getattr(instance, a.attname):
            degisiklik[_etiket(a)] = [_goster(a, eski), _goster(a, instance)]
            if a.name in SOYUT_IPTAL and getattr(instance, a.attname) is True:
                iptal_oldu = True
    if degisiklik:                                   # hiçbir şey değişmediyse günlük kirletilmez
        yaz("IPTAL" if iptal_oldu else "DEGISTI", ad, instance, degisiklik)


def _silinince(sender, instance, **kw):
    if _sessiz.get():
        return
    degisiklik = {_etiket(a): [_goster(a, instance), None] for a in _alanlar(sender)
                  if _goster(a, instance) is not None}
    yaz("SILINDI", _model_adi(sender), instance, degisiklik)


def _giris(sender, request, user, **kw):
    yaz("GIRIS", "Kullanıcı", user, kullanici=user.get_username(), ayrinti="Oturum açıldı.")


def _cikis(sender, request, user, **kw):
    if user is not None:
        yaz("CIKIS", "Kullanıcı", user, kullanici=user.get_username(), ayrinti="Oturum kapatıldı.")


def _giris_hatasi(sender, credentials, request=None, **kw):
    ad = str((credentials or {}).get("username", ""))[:150]
    yaz("GIRIS_HATASI", "Kullanıcı", kullanici=ad or "bilinmiyor", ayrinti=f"Hatalı giriş denemesi: '{ad}'")


def baglan():
    """apps.ready() içinden bir kez çağrılır."""
    from django.contrib.auth import get_user_model

    from .models import (Belge, BelgeKalem, Cari, Ek, EkstreMutabakat, EkstreSatiri, GunSonu, Hesap,
                         KasaHareketi, KasaKategori)
    izlenen = [Cari, Belge, BelgeKalem, EkstreMutabakat, EkstreSatiri, Hesap, KasaKategori, KasaHareketi,
               GunSonu, Ek, get_user_model()]
    for m in izlenen:
        uid = f"gunluk_{m._meta.label_lower}"
        pre_save.connect(_kayit_oncesi, sender=m, dispatch_uid=uid + "_pre")
        post_save.connect(_kayit_sonrasi, sender=m, dispatch_uid=uid + "_post")
        post_delete.connect(_silinince, sender=m, dispatch_uid=uid + "_del")
    user_logged_in.connect(_giris, dispatch_uid="gunluk_giris")
    user_logged_out.connect(_cikis, dispatch_uid="gunluk_cikis")
    user_login_failed.connect(_giris_hatasi, dispatch_uid="gunluk_giris_hatasi")


class KullaniciIzlemeMiddleware:
    """İstek boyunca kayıt değişikliklerini yapan kullanıcıyı belirler."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        kullanici = getattr(request, "user", None)
        ad = kullanici.get_username() if kullanici is not None and kullanici.is_authenticated else "anonim"
        with kullanici_olarak(ad):
            return self.get_response(request)
