from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .fields import kurus_bicimle
from .models import (Belge, BelgeKalem, Cari, EkstreMutabakat, EkstreSatiri, GunSonu, Hesap,
                     KasaHareketi, KasaKategori)


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


@admin.action(description="Seçili kasa hareketlerini iptal et (neden: 'Toplu iptal')")
def kasa_iptal_et(modeladmin, request, queryset):
    """Toplu iptal; kapalı gün ve eksi bakiye kuralları tek tek uygulanır."""
    iptal, reddedilen = 0, []
    for h in queryset.filter(iptal=False):
        h.iptal, h.iptal_nedeni = True, "Toplu iptal"
        try:
            h.full_clean()
            h.save()
            iptal += 1
        except ValidationError as e:
            reddedilen.append(f"{h}: {' '.join(e.messages)}")
    if iptal:
        messages.info(request, f"{iptal} kasa hareketi iptal edildi.")
    for r in reddedilen:
        messages.error(request, f"İptal edilemedi — {r}")


@admin.register(KasaHareketi)
class KasaHareketiAdmin(SilmeKapali, admin.ModelAdmin):
    list_display = ("tarih", "hesap", "yon", "tutar", "kategori", "cari", "aciklama", "iptal")
    list_filter = ("hesap", "yon", "kategori", "iptal")
    search_fields = ("aciklama", "makbuz_no", "cari__unvan")
    date_hierarchy = "tarih"
    actions = [kasa_iptal_et]
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


class EkstreSatiriInline(admin.TabularInline):
    model = EkstreSatiri
    extra = 0
    autocomplete_fields = ("belge",)
    fields = ("sira", "belge", "tarih", "tur_metni", "ekstre_evrak_no", "ekstre_tutar_kurus",
              "fark", "durum", "aciklama")
    readonly_fields = ("fark", "durum")

    @admin.display(description="Fark (₺)")
    def fark(self, obj):
        return kurus_bicimle(obj.fark_kurus) if obj.pk else "—"

    @admin.display(description="Durum")
    def durum(self, obj):
        return obj.durum_etiketi if obj.pk else "—"


@admin.register(EkstreMutabakat)
class EkstreMutabakatAdmin(admin.ModelAdmin):
    list_display = ("cari", "ekstre_tarihi", "ekstre_bakiye")
    inlines = [EkstreSatiriInline]

    @admin.display(description="Ekstre bakiyesi (₺)")
    def ekstre_bakiye(self, obj):
        return kurus_bicimle(obj.ekstre_bakiye_kurus)


@admin.register(GunSonu)
class GunSonuAdmin(SilmeKapali, admin.ModelAdmin):
    """Kapanışlar Kasa > Gün sonu ekranından yapılır. Burada yalnızca görülür; kilit kaldırma (kilitli
    kutusu) bilinçli ve nadir bir işlemdir."""

    list_display = ("tarih", "hesap", "beklenen", "sayilan", "fark", "kilitli", "fark_islendi")
    list_filter = ("hesap", "kilitli")
    readonly_fields = ("hesap", "tarih", "beklenen_kurus", "sayilan_kurus", "fark_kurus", "fark_islendi",
                       "aciklama")
    fields = readonly_fields + ("kilitli",)

    def has_add_permission(self, request):
        return False

    @admin.display(description="Kayıtlı bakiye (₺)")
    def beklenen(self, obj):
        return kurus_bicimle(obj.beklenen_kurus)

    @admin.display(description="Sayılan (₺)")
    def sayilan(self, obj):
        return kurus_bicimle(obj.sayilan_kurus)

    @admin.display(description="Fark (₺)")
    def fark(self, obj):
        return kurus_bicimle(obj.fark_kurus)
