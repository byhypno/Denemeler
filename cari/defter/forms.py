from django import forms

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .fields import KurusFormField, kurus_bicimle, ondalik_ayristir, tl_ayristir
from . import malzeme_servisi, metin
from .kdv import KdvModu, kdv_hesapla, oranlari_dogrula
from .models import Belge, BelgeKalem, Cari, KasaHareketi, KasaKategori


def _temiz_satir(deger: str) -> str:
    """Denetim karakterlerini (\x0b, \x01 …) atar, boşlukları tek aralığa indirir."""
    return " ".join("".join(c if c.isprintable() or c.isspace() else " " for c in (deger or "")).split())


class KasaHareketiDuzeltForm(forms.ModelForm):
    """Yalnızca üst veri: tutar, tarih ve yön değişmez (bakiye ve kapanışlar bozulmasın). Yanlış tutar için iptal + yeni kayıt."""

    class Meta:
        model = KasaHareketi
        fields = ["kategori", "harcayan", "makbuz_no", "aciklama"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kategori"].queryset = KasaKategori.objects.filter(aktif=True)
        self.fields["harcayan"].widget.attrs.update({"list": "harcayan-listesi", "autocomplete": "off"})

    def clean_harcayan(self):
        return _temiz_satir(self.cleaned_data.get("harcayan", ""))

    def clean_aciklama(self):
        return _temiz_satir(self.cleaned_data.get("aciklama", ""))

    def clean_makbuz_no(self):
        return _temiz_satir(self.cleaned_data.get("makbuz_no", ""))


class KasaHareketiForm(forms.ModelForm):
    class Meta:
        model = KasaHareketi
        fields = ["tarih", "yon", "tutar_kurus", "kategori", "harcayan", "makbuz_no",
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
        if "kdv_modu" in self.fields:
            self.fields["kdv_modu"].label = "KDV"
        self.fields["harcayan"].widget.attrs.update({"list": "harcayan-listesi", "autocomplete": "off", "placeholder": "ör. Mehmet"})

    def clean_harcayan(self):
        return _temiz_satir(self.cleaned_data.get("harcayan", ""))

    def clean_aciklama(self):
        return _temiz_satir(self.cleaned_data.get("aciklama", ""))

    def clean_makbuz_no(self):
        return _temiz_satir(self.cleaned_data.get("makbuz_no", ""))


class KasaTopluSatirForm(KasaHareketiForm):
    """Toplu giriş satırı: tek kayıtlık formun KDV'siz hâli (KDV 'bilinmiyor' kalır; gerekirse kayıt sonra tek tek düzenlenir)."""

    class Meta(KasaHareketiForm.Meta):
        fields = ["tarih", "yon", "tutar_kurus", "kategori", "harcayan", "makbuz_no", "aciklama"]


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

    yine_de = forms.BooleanField(required=False, label="Uyarıyı gördüm; yine de kaydet")

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
        self.fields["tutar_kurus"].required = False      # kalem girilmişse toplamı alınır; clean() zorunluluğu denetler
        self.kalem_satirlari = self._kalem_oku(self.data) if self.is_bound else []
        self.kalemler_temiz = []

    # ---- fiş kalemleri (yalnızca alış fişi/faturası)
    ALANLAR = ("aciklama", "miktar", "birim", "fiyat", "tutar")

    @classmethod
    def _kalem_oku(cls, veri):
        try:
            n = max(0, min(int(veri.get("kalem_sayisi") or 0), 200))
        except ValueError:
            n = 0
        return [{k: (veri.get(f"kalem_{k}_{i}") or "").strip() for k in cls.ALANLAR} for i in range(n)]

    def _kalemleri_coz(self):
        """Dolu satırları doğrular. Dönüş: [(aciklama, miktar, birim, birim_fiyat, tutar_kurus)]; hatalar form hatası olur."""
        temiz = []
        for no, k in enumerate(self.kalem_satirlari, start=1):
            if not any(k.values()):
                continue
            try:
                if not k["aciklama"]:
                    raise ValueError("açıklama yazın")
                if len(k["aciklama"]) > 250:
                    raise ValueError("açıklama en fazla 250 karakter olabilir")
                try:
                    miktar = ondalik_ayristir(k["miktar"], 3) if k["miktar"] else Decimal(1)
                except ValueError:
                    raise ValueError("miktarı 1,5 biçiminde girin")
                if miktar <= 0:
                    raise ValueError("miktar sıfırdan büyük olmalı")
                if miktar >= Decimal(10) ** 11:
                    raise ValueError("miktar çok büyük")
                try:
                    fiyat = ondalik_ayristir(k["fiyat"], 4) if k["fiyat"] else None
                except ValueError:
                    raise ValueError("birim fiyatı 1.234,50 biçiminde girin")
                try:
                    tutar = tl_ayristir(k["tutar"]) if k["tutar"] else None
                except ValueError:
                    raise ValueError("tutarı 1.234,50 biçiminde girin")
                if fiyat is not None and fiyat <= 0:
                    raise ValueError("birim fiyat sıfırdan büyük olmalı")
                if tutar is None and fiyat is not None:
                    tutar = int((miktar * fiyat * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                if tutar is None:
                    raise ValueError("tutar ya da birim fiyat girin")
                if tutar <= 0:
                    raise ValueError("tutar sıfırdan büyük olmalı")
                temiz.append((k["aciklama"], miktar, k["birim"][:20], fiyat, tutar))
            except ValueError as e:
                k["hata"] = str(e)
                self.add_error(None, f"Kalem {no}: {e}.")
        return temiz

    def clean(self):
        d = super().clean()
        tur, no = d.get("tur"), (d.get("evrak_no") or "").strip()
        kalemler = self._kalemleri_coz()
        if kalemler and tur not in (Belge.Tur.ALIS_FISI, Belge.Tur.ALIS_FATURASI):
            self.add_error(None, "Fiş kalemleri yalnızca alış fişi veya alış faturasında girilir.")
            kalemler = []
        toplam = sum(k[4] for k in kalemler)
        if not d.get("tutar_kurus"):
            if kalemler:
                d["tutar_kurus"] = toplam          # fiş tutarı boş: kalemlerin toplamı
            elif "tutar_kurus" not in self.errors:
                self.add_error("tutar_kurus", "Tutarı girin ya da kalem ekleyin.")
        elif kalemler and toplam != d["tutar_kurus"] and not d.get("yine_de"):
            self.yinelenme = True
            self.add_error(None, f"Kalemlerin toplamı ({kurus_bicimle(toplam)} ₺) fiş tutarından ({kurus_bicimle(d['tutar_kurus'])} ₺) farklı. "
                                 "Doğruysa 'Uyarıyı gördüm; yine de kaydet' kutusunu işaretleyip tekrar kaydedin; ya da tutarı boş bırakın, toplam kalemlerden alınsın.")
        self.kalemler_temiz = kalemler
        if tur != Belge.Tur.ODEME:
            d["odeme_sekli"] = ""                      # ödeme şekli yalnızca ödemede anlamlı
            self.instance.odeme_sekli = ""
        if tur and no:
            if Belge.objects.filter(cari=self.cari, tur=tur, evrak_no=no, iptal=False).exists():
                self.add_error("evrak_no", f"Bu tedarikçide {no} numaralı {dict(Belge.Tur.choices)[tur].lower()} zaten kayıtlı.")
        if tur and d.get("tarih") and d.get("tutar_kurus") and not self.errors and not self.yinelenme:
            benzer = Belge.objects.filter(cari=self.cari, tur=tur, tarih=d["tarih"], iptal=False)
            odenecek = self._odenecek_tutar(d)             # KDV'li girişte veritabanına yazılacak (çevrilmiş) tutar
            if any(b.tutar_kurus in (odenecek, d["tutar_kurus"]) for b in benzer) \
                    and not d.get("yine_de"):
                self.yinelenme = True
                raise forms.ValidationError(
                    "Aynı gün aynı türde aynı tutarda bir kayıt zaten var. Çift giriş olmadığından eminseniz "
                    "'Uyarıyı gördüm; yine de kaydet' kutusunu işaretleyip tekrar kaydedin.")
        return d

    @staticmethod
    def _odenecek_tutar(d) -> int:
        """Girilen tutarın KDV/tevkifat çevrimi sonrası bakiyeye etki edecek hali (geçersiz KDV girişinde girilen tutar)."""
        tutar, mod, oran = d["tutar_kurus"], d.get("kdv_modu"), d.get("kdv_orani")
        if mod in (KdvModu.HARIC, KdvModu.DAHIL) and oran is not None:
            try:
                oranlari_dogrula(oran, d.get("tevkifat_orani"))
                return kdv_hesapla(tutar, oran, mod, d.get("tevkifat_orani"))["odenecek_kurus"]
            except ValueError:
                return tutar
        return tutar

    def save(self, commit=True):
        """Belge + fiş kalemleri TEK işlemde kaydedilir (biri başarısızsa hiçbiri kalmaz)."""
        with transaction.atomic():
            belge = super().save(commit=True)
            self.olusan_kalemler = []
            harita = malzeme_servisi.katla_haritasi()
            for sira, (aciklama, miktar, birim, fiyat, tutar) in enumerate(self.kalemler_temiz, start=1):
                malzeme, _ = malzeme_servisi.malzeme_bul_veya_olustur(aciklama, birim, harita)     # katalog kendiliğinden büyür
                self.olusan_kalemler.append(BelgeKalem.objects.create(
                    belge=belge, malzeme=malzeme, sira=sira, aciklama=aciklama, miktar=miktar, birim=birim,
                    birim_fiyat=fiyat, tutar_kurus=tutar))
        return belge
