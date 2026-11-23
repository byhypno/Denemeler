"""Giriş / çıkış / parola; hatalı girişte geçici kilit."""
from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from . import gunluk
from .yetki import oturum_gerekli

ESIK = 5          # bu kadar art arda hatalı denemeden sonra
KILIT_SANIYE = 300  # bu kadar süre giriş denemesi reddedilir


def _hata_anahtari(kullanici: str) -> str:
    return "giris_hata:" + (kullanici or "").strip().lower()


def _kilit_anahtari(kullanici: str) -> str:
    return "giris_kilit:" + (kullanici or "").strip().lower()


class SinirliGirisMixin:
    """Aynı kullanıcı adına art arda hatalı denemeyi sınırlar (kaba kuvvetle parola denemeyi yavaşlatır)."""

    def clean(self):
        ad = self.data.get("username", "")
        if cache.get(_kilit_anahtari(ad)):
            raise ValidationError(
                "Çok fazla hatalı deneme. Güvenlik için bu kullanıcı adıyla giriş birkaç dakika kapatıldı; "
                "lütfen daha sonra tekrar deneyin.", code="kilitli")
        try:
            sonuc = super().clean()
        except ValidationError:
            n = cache.get(_hata_anahtari(ad), 0) + 1
            cache.set(_hata_anahtari(ad), n, KILIT_SANIYE)
            if n >= ESIK:
                cache.set(_kilit_anahtari(ad), True, KILIT_SANIYE)
                gunluk.yaz("GIRIS_HATASI", "Kullanıcı", kullanici=ad[:150] or "bilinmiyor",
                           ayrinti=f"'{ad[:150]}' için {ESIK} hatalı denemeden sonra giriş geçici olarak kapatıldı.")
            raise
        cache.delete(_hata_anahtari(ad))
        return sonuc


class GirisFormu(SinirliGirisMixin, AuthenticationForm):
    pass


class AdminGirisFormu(SinirliGirisMixin, AdminAuthenticationForm):
    pass


class GirisView(LoginView):
    template_name = "defter/giris.html"
    authentication_form = GirisFormu
    redirect_authenticated_user = True


class ParolaView(PasswordChangeView):
    template_name = "defter/parola.html"
    success_url = reverse_lazy("dashboard")

    def dispatch(self, request, *a, **kw):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *a, **kw)

    def form_valid(self, form):
        messages.success(self.request, "Parolanız değiştirildi.")
        gunluk.yaz("DEGISTI", "Kullanıcı", self.request.user, {"Parola": ["***", "***"]},
                   ayrinti="Kullanıcı kendi parolasını değiştirdi.")
        return super().form_valid(form)


@oturum_gerekli
@require_POST
def cikis(request):
    logout(request)
    return redirect("giris")
