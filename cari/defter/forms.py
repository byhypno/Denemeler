from django import forms

from .fields import KurusFormField, kurus_bicimle
from . import metin
from .models import Belge, Cari, KasaHareketi, KasaKategori


class KasaHareketiForm(forms.ModelForm):
    class Meta:
        model = KasaHareketi
        fields = ["tarih", "yon", "tutar_kurus", "kategori", "makbuz_no",
                  "aciklama", "kdv_modu", "kdv_orani", "tevkifat_orani"]
        widgets = {"tarih": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, hesap, **kwargs):
        super().__init__(*args, **kwargs)
        self.hesap = hesap
        self.instance.hesap = hesap          # model.clean() hesap bilgisine ihtiyaç duyar
        self.fields["kategori"].queryset = KasaKategori.objects.filter(aktif=True)
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


GIRILEBILIR_TURLER = [Belge.Tur.ALIS_FISI, Belge.Tur.ALIS_FATURASI, Belge.Tur.ODEME, Belge.Tur.IADE,
                      Belge.Tur.DUZELTME_ARTI, Belge.Tur.DUZELTME_EKSI]       # Açılış/Devir yalnızca yönetim panelinden


class BelgeForm(forms.ModelForm):
    """Cari ekstresinden yeni cari hareketi (alış fişi/faturası, ödeme, iade, düzeltme). Cari URL'den gelir, formda seçilmez.

    Kayıt, yönetim panelindeki ile AYNI model kurallarına tabidir (KDV, tutar > 0). Ek olarak:
    - aynı cari + tür + evrak no ikinci kez girilemez (veritabanı kısıtı da vardır);
    - aynı gün + aynı tür + aynı tutar zaten varsa uyarılır ve 'yine de kaydet' onayı istenir (çift giriş koruması)."""

    yine_de = forms.BooleanField(required=False, label="Benzer kayıt var; yine de kaydet")

    class Meta:
        model = Belge
        fields = ["tur", "tarih", "evrak_no", "harici_evrak_no", "aciklama", "odeme_sekli",
                  "tutar_kurus", "kdv_modu", "kdv_orani", "tevkifat_orani"]
        widgets = {"tarih": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
        labels = {"evrak_no": "Fiş / evrak no", "harici_evrak_no": "Tedarikçi evrak no", "odeme_sekli": "Ödeme şekli (ödemelerde)"}

    def __init__(self, *args, cari, **kwargs):
        super().__init__(*args, **kwargs)
        self.cari = cari
        self.instance.cari = cari
        self.yinelenme = False
        self.fields["tur"].choices = [(t.value, t.label) for t in GIRILEBILIR_TURLER]
        self.fields["tutar_kurus"].label = "Tutar (₺)"
        self.fields["tutar_kurus"].help_text = ""
        self.fields["tutar_kurus"].widget.attrs.update({"placeholder": "1.234,50", "inputmode": "decimal"})
        self.fields["kdv_modu"].label = "KDV"
        self.fields["odeme_sekli"].required = False

    def clean(self):
        d = super().clean()
        tur, no = d.get("tur"), (d.get("evrak_no") or "").strip()
        if tur != Belge.Tur.ODEME:
            d["odeme_sekli"] = ""                      # ödeme şekli yalnızca ödemede anlamlı
            self.instance.odeme_sekli = ""
        if tur and no:
            if Belge.objects.filter(cari=self.cari, tur=tur, evrak_no=no, iptal=False).exists():
                self.add_error("evrak_no", f"Bu tedarikçide {no} numaralı {dict(Belge.Tur.choices)[tur].lower()} zaten kayıtlı.")
        if tur and d.get("tarih") and d.get("tutar_kurus") and not self.errors:
            benzer = Belge.objects.filter(cari=self.cari, tur=tur, tarih=d["tarih"], iptal=False)
            if any(b.tutar_kurus == self.instance.efektif_tutar_kurus() or b.tutar_kurus == d["tutar_kurus"] for b in benzer) \
                    and not d.get("yine_de"):
                self.yinelenme = True
                raise forms.ValidationError(
                    "Aynı gün aynı türde aynı tutarda bir kayıt zaten var. Çift giriş olmadığından eminseniz "
                    "'Benzer kayıt var; yine de kaydet' kutusunu işaretleyip tekrar kaydedin.")
        return d
