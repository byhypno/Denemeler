from django.urls import path

from . import ek_views, gider_views, giris, kasa_views, views

urlpatterns = [
    path("giris/", giris.GirisView.as_view(), name="giris"),
    path("cikis/", giris.cikis, name="cikis"),
    path("parola/", giris.ParolaView.as_view(), name="parola"),
    path("", views.dashboard, name="dashboard"),
    path("mutabakat/", views.mutabakat_liste, name="mutabakat_liste"),
    path("mutabakat/<int:pk>/", views.mutabakat_detay, name="mutabakat_detay"),
    path("tedarikciler/", views.tedarikciler, name="tedarikciler"),
    path("tedarikciler/yeni/", views.tedarikci_form, name="tedarikci_yeni"),
    path("tedarikciler/<int:pk>/duzenle/", views.tedarikci_form, name="tedarikci_duzenle"),
    path("cari/<int:pk>/belge/yeni/", views.belge_yeni, name="belge_yeni"),
    path("belge/<int:pk>/iptal/", views.belge_iptal, name="belge_iptal"),
    path("cari/<int:pk>/ekstre/", views.cari_ekstre, name="cari_ekstre"),
    path("giderler/", gider_views.giderler, name="giderler"),
    path("giderler/kategori/", gider_views.gider_kategori_ekle, name="gider_kategori_ekle"),
    path("rapor/", views.aylik_rapor, name="aylik_rapor"),
    path("takvim/", views.odeme_takvimi, name="odeme_takvimi"),
    path("odemeler/", views.odeme_listesi, name="odeme_listesi"),
    path("yedek/", views.yedek_sayfasi, name="yedek_sayfasi"),
    path("gunluk/", views.gunluk_sayfasi, name="gunluk_sayfasi"),
    path("yedek/al/", views.yedek_al, name="yedek_al"),
    path("ekler/", ek_views.ek_depo, name="ek_depo"),
    path("ekler/<str:tur>/<int:pk>/", ek_views.ek_sahip, name="ek_sahip"),
    path("ek/<int:pk>/indir/", ek_views.ek_indir, name="ek_indir"),
    path("ek/<int:pk>/kaldir/", ek_views.ek_kaldir, name="ek_kaldir"),
    path("kasa/", kasa_views.kasa_ana, name="kasa"),
    path("kasa/hareket/<int:pk>/iptal/", kasa_views.kasa_hareket_iptal, name="kasa_hareket_iptal"),
    path("kasa/gun-sonu/", kasa_views.kasa_gun_sonu, name="kasa_gun_sonu"),
]
