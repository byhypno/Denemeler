"""Rollerin (grupların) kurulumu ve kullanıcı-rol senkronu."""
from django.contrib.auth.models import Group, Permission

from . import gunluk
from .yetki import ROL_YETENEKLERI

# Muhasebe, yönetim panelinde bu modellerde ekleme/değiştirme/görme yapabilir (silme YOK: uygulamada silme yok).
MUHASEBE_YAZAR = ["cari", "belge", "belgekalem", "ekstremutabakat", "ekstresatiri", "kasakategori", "kasahareketi"]
# Yalnızca görme (kilit/ayar/hesap/ek değişiklikleri yöneticiye aittir):
MUHASEBE_OKUR = ["hesap", "gunsonu", "ek"]


def muhasebe_izinleri():
    kodlar = [f"{hak}_{m}" for m in MUHASEBE_YAZAR for hak in ("add", "change", "view")]
    kodlar += [f"view_{m}" for m in MUHASEBE_OKUR]
    return Permission.objects.filter(content_type__app_label="defter", codename__in=kodlar)


def rolleri_kur():
    """Idempotent: rol gruplarını oluşturur ve izinlerini kanonik haline getirir."""
    for ad in ROL_YETENEKLERI:
        grup, _ = Group.objects.get_or_create(name=ad)
        grup.permissions.set(muhasebe_izinleri() if ad == "Muhasebe" else [])


def kullaniciyi_senkronla(user):
    """Muhasebe rolü yönetim paneline girer (is_staff); diğer roller panele girmez."""
    istenen = user.is_superuser or user.groups.filter(name="Muhasebe").exists()
    if user.is_staff != istenen:
        user.is_staff = istenen
        user.save(update_fields=["is_staff"])


def _gruplar_degisti(sender, instance, action, reverse, pk_set, **kw):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    from django.contrib.auth import get_user_model
    User = get_user_model()
    kullanicilar = [instance] if not reverse else list(User.objects.filter(pk__in=pk_set or []))
    for u in kullanicilar:
        kullaniciyi_senkronla(u)
        roller = ", ".join(sorted(u.groups.values_list("name", flat=True))) or "(rol yok)"
        gunluk.yaz("DEGISTI", "Kullanıcı", u, {"Roller": [None, roller]}, ayrinti="Kullanıcının rolleri değişti.")


def _migrate_sonrasi(sender, **kw):
    rolleri_kur()


def baglan(app_config):
    from django.contrib.auth import get_user_model
    from django.db.models.signals import m2m_changed, post_migrate
    # Not: sinyal alıcıları varsayılan olarak ZAYIF referansla tutulur; `lambda` kullanmak alıcının çöp toplayıcı
    # tarafından silinmesine ve rollerin hiç kurulmamasına yol açar. Modül düzeyinde işlev + weak=False.
    post_migrate.connect(_migrate_sonrasi, sender=app_config, weak=False, dispatch_uid="defter_roller_kur")
    m2m_changed.connect(_gruplar_degisti, sender=get_user_model().groups.through, dispatch_uid="defter_rol_senkron")
