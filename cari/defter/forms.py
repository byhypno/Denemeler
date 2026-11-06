from django import forms

from .fields import KurusFormField
from .models import Belge, Cari, KasaHareketi, KasaKategori


class _OdemeSecim(forms.ModelChoiceField):
    def label_from_instance(self, b):
        return f"{b.tarih:%d.%m.%Y} · {b.cari} · {b.tutar_kurus // 100:,}".replace(",", ".") + " ₺"


class KasaHareketiForm(forms.ModelForm):
    ilgili_odeme = _OdemeSecim(queryset=Belge.objects.none(), required=False,
                               label="İlgili cari ödemesi (isteğe bağlı)")

    class Meta:
        model = KasaHareketi
        fields = ["tarih", "yon", "tutar_kurus", "kategori", "cari", "ilgili_odeme",
                  "makbuz_no", "aciklama", "kdv_modu", "kdv_orani", "tevkifat_orani"]
        widgets = {"tarih": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, hesap, **kwargs):
        super().__init__(*args, **kwargs)
        self.hesap = hesap
        self.instance.hesap = hesap          # model.clean() hesap bilgisine ihtiyaç duyar
        self.fields["kategori"].queryset = KasaKategori.objects.filter(aktif=True)
        self.fields["cari"].queryset = Cari.objects.filter(aktif=True)
        bagli = KasaHareketi.objects.filter(iptal=False, ilgili_odeme__isnull=False) \
            .values_list("ilgili_odeme_id", flat=True)
        self.fields["ilgili_odeme"].queryset = Belge.objects.filter(
            tur=Belge.Tur.ODEME, iptal=False).exclude(pk__in=bagli).select_related("cari").order_by("-tarih")
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
