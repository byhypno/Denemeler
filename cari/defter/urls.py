from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("mutabakat/", views.mutabakat_liste, name="mutabakat_liste"),
    path("mutabakat/<int:pk>/", views.mutabakat_detay, name="mutabakat_detay"),
    path("cari/<int:pk>/ekstre/", views.cari_ekstre, name="cari_ekstre"),
]
