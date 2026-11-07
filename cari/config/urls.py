from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Cari"
admin.site.site_title = "Cari"
admin.site.site_url = "/"
admin.site.index_title = "Cari ve Kasa Yönetimi"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("defter.urls")),
]
