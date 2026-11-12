from . import yedek, yetki


def genel(request):
    """Her sayfada: kullanıcının yetenekleri/rolü ve (yalnızca yönetici için) yedek uyarısı."""
    kullanici = getattr(request, "user", None)
    if kullanici is None or not kullanici.is_authenticated:
        return {}
    ctx = {"yetkiler": yetki.yetenekler(kullanici), "rol_etiketi": yetki.rol_etiketi(kullanici)}
    if kullanici.is_superuser:
        try:
            ctx["yedek_durumu"] = yedek.yedek_durumu()
        except Exception:        # uyarı hiçbir sayfayı bozmamalı (ör. geçiş sırasında tablo yoksa)
            pass
    return ctx
