from django import forms

from .fields import KurusFormField, kurus_bicimle
from . import metin
from .models import Belge, Cari, KasaHareketi, KasaKategori


class _OdemeSecim(forms.ModelChoiceField):
    def label_from_instance(self, b):
        return f"{b.tarih:%d.%m.%Y} · {b.cari} · {kurus_bicimle(b.tutar_kurus)} ₺"


class KasaHareketiForm(forms.ModelForm):
    ilgili_odeme = _OdemeSecim(queryset=Belge.objects.none(), required=False,
                               label="İlgili cari ödemesi (isteğe bağlı)")

    class Meta:
        model = KasaHareketi
        fields = ["tarih", "yon", "tutar_kurus", "kategori", "cari", "ilgili_odeme", "makbuz_no",
                  "aciklama", "kdv_modu", "kdv_orani", "tevkifat_orani"]
        widgets = {"tarih": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, hesap, **kwargs):
        super().__init__(*args, **kwargs)
        self.hesap = hesap
        self.instance.hesap = hesap          # model.clean() hesap bilgisine ihtiyaç duyar
        self.fields["kategori"].queryset = KasaKategori.objects.filter(aktif=True)
        if hesap.cari_bagli:
            self.fields["cari"].queryset = Cari.objects.filter(aktif=True)
            bagli = KasaHareketi.objects.filter(iptal=False, ilgili_odeme__isnull=False) \
                .values_list("ilgili_odeme_id", flat=True)
            self.fields["ilgili_odeme"].queryset = Belge.objects.filter(
                tur=Belge.Tur.ODEME, iptal=False).exclude(pk__in=bagli).select_related("cari").order_by("-tarih")
        else:
            # Ofis Kasa cari defterinden bağımsızdır: bu alanlar formda hiç görünmez.
            del self.fields["cari"]
            del self.fields["ilgili_odeme"]
        self.fields["tutar_kurus"].label = "Tutar (₺)"
        self.fields["tutar_kurus"].help_text = ""
        self.fields["tutar_kurus"].widget.attrs.update({"placeholder": "1.234,50", "inputmode": "decimal"})
        self.fields["kdv_modu"].label = "KDV"


class GunSonuForm(forms.Form):
    tarih = forms.DateField(label="Kapanış günü",
                            widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    sayilan = KurusFormField(label="Sayılan nakit (₺)",
                             widget=forms.TextInput(attrs={"placeholder": "1.234,50", "inputmode": "decimal"}))
    aciklama = forms.CharField(label="Açıklama", required=False, max_length=250)
    farki_isle = forms.BooleanField(
        label="Fark varsa kasa hareketi olarak işle (kategori: Kasa farkı)", required=False)


class CariForm(forms.ModelForm):
    """Tedarikçi ekleme/düzenleme. Ünvan, büyük/küçük harf ve aksan farkı yok sayılarak da benzersiz olmalı
    ('ERÖZ' ile 'Eroz' aynı tedarikçidir; iki ayrı cari açılıp bakiyeler bölünmesin)."""

    class Meta:
        model = Cari
        fields = ["unvan", "kisa_kod", "vergi_bilgisi", "yetkili", "telefon", "eposta",
                  "vade_gun", "tedarikcideki_kodumuz", "not_metni", "aktif"]
        widgets = {"not_metni": forms.Textarea(attrs={"rows": 3}), "vade_gun": forms.NumberInput(attrs={"min": 0, "max": 365})}
        labels = {"unvan": "Ünvan", "kisa_kod": "Kısa kod", "vergi_bilgisi": "Vergi dairesi / no", "yetkili": "Yetkili kişi",
                  "telefon": "Telefon", "eposta": "E-posta", "vade_gun": "Ödeme vadesi (gün)",
                  "tedarikcideki_kodumuz": "Tedarikçideki cari kodumuz", "not_metni": "Not", "aktif": "Aktif tedarikçi"}
        help_texts = {"vade_gun": "Boş bırakılırsa vade takibi yapılmaz.", "aktif": "Pasif tedarikçi yeni kayıt seçeneklerinde çıkmaz; geçmişi durur."}

    def clean_unvan(self):
        unvan = " ".join(self.cleaned_data["unvan"].split())
        ayni = [c for c in Cari.objects.exclude(pk=self.instance.pk) if metin.katla(c.unvan) == metin.katla(unvan)]
        if ayni:
            raise forms.ValidationError(f"Bu tedarikçi zaten kayıtlı: {ayni[0].unvan}")
        return unvan

    def clean_vade_gun(self):
        v = self.cleaned_data.get("vade_gun")
        if v is not None and v > 365:
            raise forms.ValidationError("Vade en fazla 365 gün olabilir.")
        return v
