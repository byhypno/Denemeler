from django.urls import path

from . import kasa_views, views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("mutabakat/", views.mutabakat_liste, name="mutabakat_liste"),
    path("mutabakat/<int:pk>/", views.mutabakat_detay, name="mutabakat_detay"),
    path("cari/<int:pk>/ekstre/", views.cari_ekstre, name="cari_ekstre"),
    path("kasa/", kasa_views.kasa_ana, name="kasa"),
    path("kasa/hareket/<int:pk>/iptal/", kasa_views.kasa_hareket_iptal, name="kasa_hareket_iptal"),
    path("kasa/gun-sonu/", kasa_views.kasa_gun_sonu, name="kasa_gun_sonu"),
]
