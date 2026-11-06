from . import yedek


def genel(request):
    """Her sayfada: yedek uyarısı (yalnızca giriş yapmış yönetici için)."""
    kullanici = getattr(request, "user", None)
    if kullanici is None or not kullanici.is_authenticated or not kullanici.is_superuser:
        return {}
    try:
        return {"yedek_durumu": yedek.yedek_durumu()}
    except Exception:           # uyarı hiçbir sayfayı bozmamalı (ör. geçiş sırasında tablo yoksa)
        return {}
