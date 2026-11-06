from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

admin.site.site_header = "Cari Program"
admin.site.site_title = "Cari Program"
admin.site.index_title = "Cari ve Kasa Yönetimi"

urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", admin.site.urls),
]
