from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


def rol_kullanici(ad, rol=None, parola="Guclu-Parola-9", **kw):
    """Rolü atanmış (ya da rolsüz) test kullanıcısı. rol: Muhasebe | Kasiyer | Görüntüleyici | None."""
    u = get_user_model().objects.create_user(ad, password=parola, **kw)
    if rol:
        u.groups.add(Group.objects.get(name=rol))
        u.refresh_from_db()
    return u


def cari_kasa_ac():
    """Cari bağlantılı kasanın GENEL mekaniğini (giriş+çıkış, eksiye düşememe, kontrol sayfası) sınayan testler için:
    Cari Kasa'yı bu mekaniğe döndürür. Gerçek varsayılan farklıdır: Cari Kasa yalnızca tedarikçi ödemesi (çıkış)
    tutar, bakiyesi hep eksidir (geçiş 0013); onu sınayan testler bu yardımcıyı KULLANMAZ."""
    from .models import Hesap
    h = Hesap.objects.get(ad="Cari Kasa")
    h.aktif, h.sadece_cikis, h.eksiye_dusebilir, h.on_yuzde_gizli = True, False, False, False
    h.save()
    return h


def cari_kasa_goster():
    """Cari Kasa'yı ön yüzde görünür yapar (ayarlar aynen kalır: yalnızca çıkış). Varsayılan GİZLİDİR (geçiş 0014)."""
    from .models import Hesap
    h = Hesap.objects.get(ad="Cari Kasa")
    h.on_yuzde_gizli = False
    h.save()
    return h
