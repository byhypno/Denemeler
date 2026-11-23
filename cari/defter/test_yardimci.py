from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


def rol_kullanici(ad, rol=None, parola="Guclu-Parola-9", **kw):
    """Rolü atanmış (ya da rolsüz) test kullanıcısı. rol: Muhasebe | Kasiyer | Görüntüleyici | None."""
    u = get_user_model().objects.create_user(ad, password=parola, **kw)
    if rol:
        u.groups.add(Group.objects.get(name=rol))
        u.refresh_from_db()
    return u
