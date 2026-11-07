from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.core.exceptions import ValidationError

from . import metin
from .fields import kurus_bicimle
from .models import (Belge, BelgeKalem, Cari, Ek, EkstreMutabakat, GenelGider, GiderKategori, IslemGunlugu, EkstreSatiri,
                     GunSonu, Hesap, KasaHareketi, KasaKategori, Malzeme, MalzemeKategori)


def gecmis_baglantisi(model_adi):
    """Yönetim formlarında kaydın değişiklik geçmişine (işlem günlüğü) bağlantı."""
    def _bag(self, obj):
        if not obj or not obj.pk:
            return "—"
        return format_html('<a href="{}?model={}&nesne={}">🕘 Değişiklik geçmişi</a>',
                           reverse("gunluk_sayfasi"), model_adi, obj.pk)
    _bag.short_description = "Geçmiş"
    return _bag


def ekler_baglantisi(tur):
    """Yönetim formlarında 'Ekler' sayfasına bağlantı veren salt okunur alan üretir."""
    def _bag(self, obj):
        if not obj or not obj.pk:
            return "— (önce kaydedin)"
        n = obj.ekler.filter(kaldirildi=False).count()
        return format_html('<a href="{}">📎 Ekler ({})</a>', reverse("ek_sahip", args=[tur, obj.pk]), n)
    _bag.short_description = "Ek dosyalar"
    return _bag


class SilmeKapali:
    """Kayıt silinmez; yanlışlar 'iptal' ile işaretlenir ya da düzeltme satırıyla giderilir."""

    def has_delete_permission(self, request, obj=None):
        return False


@admin.action(description="Seçili kayıtları iptal et (neden: 'Toplu iptal')")
def iptal_et(modeladmin, request, queryset):
    n = 0
    for obj in queryset.filter(iptal=False):          # tek tek kaydedilir: değişiklik işlem günlüğüne düşer
        obj.iptal, obj.iptal_nedeni = True, "Toplu iptal"
        obj.save()
        n += 1
    messages.info(request, f"{n} kayıt iptal edildi.")


class KalemInline(admin.TabularInline):
    model = BelgeKalem
    extra = 0
    autocomplete_fields = ("malzeme",)       # boş bırakılırsa açıklamadan eşlenir (BelgeKalem.save)


@admin.register(Cari)
class CariAdmin(admin.ModelAdmin):
    list_display = ("unvan", "kisa_kod", "bakiye", "vade_gun", "aktif")
    search_fields = ("unvan", "kisa_kod", "vergi_bilgisi")
    list_filter = ("aktif",)
    readonly_fields = ("ekler_bag", "gecmis_bag")
    ekler_bag = ekler_baglantisi("cari")

    def get_search_results(self, request, queryset, search_term):
        """Arama (liste ve aramalı seçim kutuları): büyük/küçük harf ve aksan farkını yok sayar ('eroz' -> 'ERÖZ').
        SQLite'ın LIKE'ı 'İ'/'i' eşleştirmez, bu yüzden Python'da süzülür (cari sayısı küçük)."""
        if not search_term.strip():
            return queryset, False
        idler = [c.pk for c in queryset if metin.eslesir(search_term, c.unvan, c.kisa_kod, c.vergi_bilgisi, c.yetkili)]
        return queryset.filter(pk__in=idler), False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # aramalı seçim kutusunda pasif tedarikçiler çıkmasın (yeni kayıt için seçilmesin); listede görünürler
        if request.path.endswith("/autocomplete/"):
            qs = qs.filter(aktif=True)
        return qs
    gecmis_bag = gecmis_baglantisi("Cari")

    @admin.display(description="Güncel borcumuz (₺)")
    def bakiye(self, obj):
        return kurus_bicimle(obj.bakiye_kurus())


@admin.register(Belge)
class BelgeAdmin(SilmeKapali, admin.ModelAdmin):
    list_display = ("tarih", "tur", "cari", "evrak_no", "harici_evrak_no", "tutar", "kdv_modu", "iptal")
    list_filter = ("tur", "cari", "iptal", "kdv_modu", "odeme_sekli")
    search_fields = ("evrak_no", "harici_evrak_no", "aciklama", "cari__unvan")
    date_hierarchy = "tarih"
    autocomplete_fields = ("cari",)
    inlines = [KalemInline]
    actions = [iptal_et]
    readonly_fields = ("matrah_tl", "kdv_tl", "tevkifat_tl", "ekler_bag", "gecmis_bag")
    ekler_bag = ekler_baglantisi("belge")
    gecmis_bag = gecmis_baglantisi("Belge")
    fieldsets = (
        (None, {"fields": ("cari", "tur", "tarih", "evrak_no", "harici_evrak_no", "aciklama",
                           "odeme_sekli", "kaynak_notu", "ekler_bag", "gecmis_bag")}),
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

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser          # kasa ayarları (eksiye düşme, cari bağlantısı) yalnızca yönetici

    def has_add_permission(self, request):
        return request.user.is_superuser

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
    list_display = ("tarih", "hesap", "yon", "tutar", "kategori", "harcayan", "aciklama", "iptal")
    list_filter = ("hesap", "yon", "kategori", "iptal")
    search_fields = ("aciklama", "makbuz_no", "harcayan")
    date_hierarchy = "tarih"
    actions = [kasa_iptal_et]
    readonly_fields = ("matrah_tl", "kdv_tl", "tevkifat_tl", "ekler_bag", "gecmis_bag")
    ekler_bag = ekler_baglantisi("kasa")
    gecmis_bag = gecmis_baglantisi("KasaHareketi")
    fieldsets = (
        (None, {"fields": ("hesap", "tarih", "yon", "kategori", "harcayan", "makbuz_no",
                           "aciklama", "ekler_bag", "gecmis_bag")}),
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
    autocomplete_fields = ("cari",)
    inlines = [EkstreSatiriInline]
    readonly_fields = ("ekler_bag",)
    ekler_bag = ekler_baglantisi("mutabakat")

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

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser          # kapanış kilidini kaldırmak yalnızca yöneticidir

    @admin.display(description="Kayıtlı bakiye (₺)")
    def beklenen(self, obj):
        return kurus_bicimle(obj.beklenen_kurus)

    @admin.display(description="Sayılan (₺)")
    def sayilan(self, obj):
        return kurus_bicimle(obj.sayilan_kurus)

    @admin.display(description="Fark (₺)")
    def fark(self, obj):
        return kurus_bicimle(obj.fark_kurus)


@admin.register(Ek)
class EkAdmin(SilmeKapali, admin.ModelAdmin):
    """Ekler Ekler sayfasından yüklenir/kaldırılır; burada yalnızca görülür."""

    list_display = ("orijinal_ad", "sahip_kisa", "icerik_turu", "boyut_bayt", "yuklenme", "kaldirildi")
    list_filter = ("icerik_turu", "kaldirildi")
    search_fields = ("orijinal_ad", "aciklama", "sha256")
    readonly_fields = [f.name for f in Ek._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(IslemGunlugu)
class IslemGunlugAdmin(admin.ModelAdmin):
    """Salt okunur: günlük eklenmez, değiştirilmez, silinmez. Asıl görünüm: Günlük sayfası."""

    list_display = ("zaman", "kullanici", "islem", "model", "nesne_ozeti")
    list_filter = ("islem", "model", "kullanici")
    search_fields = ("nesne_ozeti", "ayrinti", "kullanici")
    readonly_fields = [f.name for f in IslemGunlugu._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Yönetim paneli girişi de hatalı denemede geçici kilit uygular.
from .giris import AdminGirisFormu  # noqa: E402
admin.site.login_form = AdminGirisFormu


@admin.register(GiderKategori)
class GiderKategoriAdmin(admin.ModelAdmin):
    """Genel gider kalemleri. Silinmez; kullanılmayacaksa 'aktif' işareti kaldırılır (geçmiş tutarlar korunur)."""
    list_display = ("ad", "sira", "aktif")
    list_editable = ("sira", "aktif")
    search_fields = ("ad",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(GenelGider)
class GenelGiderAdmin(SilmeKapali, admin.ModelAdmin):
    """Aylık net genel giderler. Giriş için Genel giderler sayfasını kullanın; burası düzeltme/inceleme içindir."""
    list_display = ("yil", "ay", "kategori", "tutar", "aciklama")
    list_filter = ("yil", "ay", "kategori")
    autocomplete_fields = ()
    search_fields = ("aciklama", "kategori__ad")

    @admin.display(description="Net tutar (₺)", ordering="tutar_kurus")
    def tutar(self, obj):
        return kurus_bicimle(obj.tutar_kurus)


@admin.register(MalzemeKategori)
class MalzemeKategoriAdmin(admin.ModelAdmin):
    """Malzeme kategorileri. Silinmez; kullanılmayacaksa 'aktif' kaldırılır (malzemelerin kategorisi korunur)."""
    list_display = ("ad", "sira", "aktif")
    list_editable = ("sira", "aktif")
    search_fields = ("ad",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Malzeme)
class MalzemeAdmin(SilmeKapali, admin.ModelAdmin):
    """Malzeme kataloğu. Fiyat geçmişi Malzemeler sayfasındadır; burası düzeltme içindir."""
    list_display = ("ad", "kategori", "birim", "aktif")
    list_filter = ("kategori", "aktif")
    search_fields = ("ad",)

