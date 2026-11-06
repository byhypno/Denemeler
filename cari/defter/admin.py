from django.contrib import admin, messages

from .fields import kurus_bicimle
from .models import Belge, BelgeKalem, Cari, Hesap, KasaHareketi, KasaKategori


class SilmeKapali:
    """Kayıt silinmez; yanlışlar 'iptal' ile işaretlenir ya da düzeltme satırıyla giderilir."""

    def has_delete_permission(self, request, obj=None):
        return False


@admin.action(description="Seçili kayıtları iptal et (neden: 'Toplu iptal')")
def iptal_et(modeladmin, request, queryset):
    n = queryset.filter(iptal=False).update(iptal=True, iptal_nedeni="Toplu iptal")
    messages.info(request, f"{n} kayıt iptal edildi.")


class KalemInline(admin.TabularInline):
    model = BelgeKalem
    extra = 0


@admin.register(Cari)
class CariAdmin(admin.ModelAdmin):
    list_display = ("unvan", "kisa_kod", "bakiye", "vade_gun", "aktif")
    search_fields = ("unvan", "kisa_kod", "vergi_bilgisi")
    list_filter = ("aktif",)

    @admin.display(description="Güncel borcumuz (₺)")
    def bakiye(self, obj):
        return kurus_bicimle(obj.bakiye_kurus())


@admin.register(Belge)
class BelgeAdmin(SilmeKapali, admin.ModelAdmin):
    list_display = ("tarih", "tur", "cari", "evrak_no", "harici_evrak_no", "tutar", "kdv_modu", "iptal")
    list_filter = ("tur", "cari", "iptal", "kdv_modu", "odeme_sekli")
    search_fields = ("evrak_no", "harici_evrak_no", "aciklama", "cari__unvan")
    date_hierarchy = "tarih"
    inlines = [KalemInline]
    actions = [iptal_et]
    readonly_fields = ("matrah_tl", "kdv_tl", "tevkifat_tl")
    fieldsets = (
        (None, {"fields": ("cari", "tur", "tarih", "evrak_no", "harici_evrak_no", "aciklama",
                           "odeme_sekli", "kaynak_notu")}),
        ("Tutar ve KDV", {"fields": ("tutar_kurus", "kdv_modu", "kdv_orani", "tevkifat_orani",
                                     "matrah_tl", "kdv_tl", "tevkifat_tl")}),
        ("İptal", {"fields": ("iptal", "iptal_nedeni")}),
    )

    @admin.display(description="Tutar (₺)", ordering="tutar_kurus")
    def tutar(self, obj):
        return kurus_bicimle(obj.tutar_kurus)

    @admin.display(description="Matrah (₺)")
    def matrah_tl(self, obj):
        return kurus_bicimle(obj.matrah_kurus) or "—"

    @admin.display(description="KDV (₺)")
    def kdv_tl(self, obj):
        return kurus_bicimle(obj.kdv_kurus) or "—"

    @admin.display(description="Tevkifat (₺)")
    def tevkifat_tl(self, obj):
        return kurus_bicimle(obj.tevkifat_kurus) or "—"


@admin.register(Hesap)
class HesapAdmin(SilmeKapali, admin.ModelAdmin):
    list_display = ("ad", "tur", "bakiye", "aktif")

    @admin.display(description="Güncel bakiye (₺)")
    def bakiye(self, obj):
        return kurus_bicimle(obj.bakiye_kurus())


@admin.register(KasaKategori)
class KasaKategoriAdmin(admin.ModelAdmin):
    list_display = ("ad", "tur", "genel_gider_grubu", "aktif")


@admin.register(KasaHareketi)
class KasaHareketiAdmin(SilmeKapali, admin.ModelAdmin):
    list_display = ("tarih", "hesap", "yon", "tutar", "kategori", "cari", "aciklama", "iptal")
    list_filter = ("hesap", "yon", "kategori", "iptal")
    search_fields = ("aciklama", "makbuz_no", "cari__unvan")
    date_hierarchy = "tarih"
    actions = [iptal_et]
    readonly_fields = ("matrah_tl", "kdv_tl", "tevkifat_tl")
    fieldsets = (
        (None, {"fields": ("hesap", "tarih", "yon", "kategori", "cari", "ilgili_odeme",
                           "makbuz_no", "aciklama")}),
        ("Tutar ve KDV", {"fields": ("tutar_kurus", "kdv_modu", "kdv_orani", "tevkifat_orani",
                                     "matrah_tl", "kdv_tl", "tevkifat_tl")}),
        ("İptal", {"fields": ("iptal", "iptal_nedeni")}),
    )

    @admin.display(description="Tutar (₺)", ordering="tutar_kurus")
    def tutar(self, obj):
        return kurus_bicimle(obj.tutar_kurus)

    @admin.display(description="Matrah (₺)")
    def matrah_tl(self, obj):
        return kurus_bicimle(obj.matrah_kurus) or "—"

    @admin.display(description="KDV (₺)")
    def kdv_tl(self, obj):
        return kurus_bicimle(obj.kdv_kurus) or "—"

    @admin.display(description="Tevkifat (₺)")
    def tevkifat_tl(self, obj):
        return kurus_bicimle(obj.tevkifat_kurus) or "—"
