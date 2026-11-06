from django.urls import path

from . import ek_views, kasa_views, views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("mutabakat/", views.mutabakat_liste, name="mutabakat_liste"),
    path("mutabakat/<int:pk>/", views.mutabakat_detay, name="mutabakat_detay"),
    path("cari/<int:pk>/ekstre/", views.cari_ekstre, name="cari_ekstre"),
    path("odemeler/", views.odeme_listesi, name="odeme_listesi"),
    path("ekler/", ek_views.ek_depo, name="ek_depo"),
    path("ekler/<str:tur>/<int:pk>/", ek_views.ek_sahip, name="ek_sahip"),
    path("ek/<int:pk>/indir/", ek_views.ek_indir, name="ek_indir"),
    path("ek/<int:pk>/kaldir/", ek_views.ek_kaldir, name="ek_kaldir"),
    path("kasa/", kasa_views.kasa_ana, name="kasa"),
    path("kasa/hareket/<int:pk>/iptal/", kasa_views.kasa_hareket_iptal, name="kasa_hareket_iptal"),
    path("kasa/gun-sonu/", kasa_views.kasa_gun_sonu, name="kasa_gun_sonu"),
    path("kasa/kontrol/", kasa_views.kasa_kontrol, name="kasa_kontrol"),
]
