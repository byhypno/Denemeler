"""Roller ve yetenekler.

Roller Django 'Grup'larıdır; yönetici = superuser. Her rol bir YETENEK kümesine karşılık gelir:

  goruntule        cari tarafını (Genel Bakış, ekstre, mutabakat, ödeme listesi, ekler) görme
  kasa_goruntule   kasa sayfalarını görme
  kasa_yaz         kasa hareketi girme/iptal, gün sonu kapanışı
  cari_kasa        Cari Kasa'yı (cari bağlantılı kasa) görme/kullanma
  ek_yaz           cari tarafındaki kayıtlara ek yükleme/kaldırma
  veri_gir         eşleştirme gibi cari tarafı yazma işlemleri (veri girişi yönetim panelinden, model izinleriyle)
  yonetim          yedek, işlem günlüğü, kullanıcı yönetimi, kilit kaldırma (yalnızca yönetici)

Hiçbir rol kayıt silemez (uygulamada silme yoktur); kilit kaldırma ve hesap ayarları yalnızca yöneticidir.
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

ROL_YETENEKLERI = {
    "Muhasebe": frozenset({"goruntule", "kasa_goruntule", "kasa_yaz", "cari_kasa", "ek_yaz", "veri_gir"}),
    "Kasiyer": frozenset({"kasa_goruntule", "kasa_yaz"}),                      # yalnızca cari bağlantısız kasa
    "Görüntüleyici": frozenset({"goruntule", "kasa_goruntule", "cari_kasa"}),  # her şeyi görür, hiçbir şey yazamaz
}
YONETICI_YETENEKLERI = frozenset().union(*ROL_YETENEKLERI.values()) | {"yonetim"}


def yetenekler(user) -> frozenset:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return frozenset()
    if user.is_superuser:
        return YONETICI_YETENEKLERI
    onbellek = getattr(user, "_cari_yetenekler", None)
    if onbellek is None:
        adlar = set(user.groups.values_list("name", flat=True))
        onbellek = frozenset().union(*(ROL_YETENEKLERI.get(a, frozenset()) for a in adlar))
        user._cari_yetenekler = onbellek
    return onbellek


def var_mi(user, yetenek: str) -> bool:
    return yetenek in yetenekler(user)


def rol_etiketi(user) -> str:
    if not getattr(user, "is_authenticated", False):
        return ""
    if user.is_superuser:
        return "Yönetici"
    return ", ".join(sorted(g for g in user.groups.values_list("name", flat=True) if g in ROL_YETENEKLERI)) or "Rolsüz"


def oturum_gerekli(view):
    """Yalnızca oturum açılmış olmasını ister (ayrıntılı yetki görünüm içinde denetlenir)."""
    @wraps(view)
    def sarmal(request, *a, **kw):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return view(request, *a, **kw)
    return sarmal


def yetki_gerekli(okuma: str, yazma: str | None = None):
    """GET/HEAD için `okuma`, diğer yöntemler için `yazma` (verilmişse) yeteneği ister. Yetkisizse 403."""
    def dekor(view):
        @wraps(view)
        def sarmal(request, *a, **kw):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            gerekli = yazma if (yazma and request.method not in ("GET", "HEAD", "OPTIONS")) else okuma
            if not var_mi(request.user, gerekli):
                raise PermissionDenied("Bu işlem için yetkiniz yok.")
            return view(request, *a, **kw)
        return sarmal
    return dekor


def gorunur_kasalar(user):
    """Kullanıcının ÖN YÜZDE görebildiği kasa hesapları: aktif ve gizlenmemiş olanlar
    (Cari Kasa ayrıca yalnızca 'cari_kasa' yeteneği olanlara)."""
    from .models import Hesap
    qs = Hesap.objects.filter(aktif=True, on_yuzde_gizli=False, tur=Hesap.Tur.KASA).order_by("id")
    return qs if var_mi(user, "cari_kasa") else qs.filter(cari_bagli=False)


def ek_izni(user, sahip_turu: str, sahip, yazma: bool) -> bool:
    """Ek dosyalara erişim: kasa ekleri kasa yetkisiyle, diğerleri cari yetkisiyle."""
    if sahip_turu == "kasa":
        if not var_mi(user, "kasa_yaz" if yazma else "kasa_goruntule"):
            return False
        return (not sahip.hesap.cari_bagli) or var_mi(user, "cari_kasa")
    return var_mi(user, "ek_yaz" if yazma else "goruntule")
