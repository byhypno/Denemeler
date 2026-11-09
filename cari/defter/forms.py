from django import forms

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q

from .fields import MAKS_KURUS, KurusFormField, kurus_bicimle, ondalik_ayristir, tl_ayristir
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

    # ---- açılış bakiyesi: yeni tedarikçide girilir; mevcutta varsa gösterilir/düzeltilir, yoksa eklenir
    acilis_tutar = KurusFormField(required=False, label="Açılış bakiyesi (₺)",
                                  help_text="Programa başlarken bu tedarikçiyle aranızdaki mevcut bakiye. Yoksa boş bırakın; sonra ekstreden hareket girersiniz.")
    acilis_yon = forms.ChoiceField(required=False, label="Açılış bakiyesi yönü", initial="BORC",
                                   choices=[("BORC", "Tedarikçiye borcumuz var"), ("ALACAK", "Tedarikçiden alacağımız var (avans)")])
    acilis_tarih = forms.DateField(required=False, label="Bakiye tarihi", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
                                   help_text="Bakiyenin geçerli olduğu gün (ör. programa başladığınız gün).")
    field_order = ["unvan", "kisa_kod", "vergi_bilgisi", "yetkili", "telefon", "eposta", "vade_gun", "tedarikcideki_kodumuz",
                   "acilis_tutar", "acilis_yon", "acilis_tarih", "not_metni", "aktif"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.acilis_belge = self._acilis_belgesi()
        if self.acilis_belge is not None and not self.is_bound:
            b = self.acilis_belge
            self.initial["acilis_tutar"] = b.tutar_kurus
            self.initial["acilis_yon"] = "ALACAK" if b.tur == Belge.Tur.DUZELTME_EKSI else "BORC"
            self.initial["acilis_tarih"] = b.tarih

    def _acilis_belgesi(self):
        """Bu tedarikçinin aktif açılış kaydı: 'Açılış / Devir' türü ya da bu formdan girilen alacak/avans açılışı (en yenisi)."""
        if not self.instance.pk:
            return None
        qs = Belge.objects.filter(cari=self.instance, iptal=False).filter(
            Q(tur=Belge.Tur.ACILIS) | Q(tur=Belge.Tur.DUZELTME_EKSI, aciklama__startswith="Açılış bakiyesi"))
        return qs.order_by("-id").first()

    def clean_acilis_tarih(self):
        t = self.cleaned_data.get("acilis_tarih")
        if t is not None and not (2000 <= t.year <= 2100):
            raise forms.ValidationError("Tarih 2000–2100 yılları arasında olmalı.")
        return t

    def clean(self):
        d = super().clean()
        if d.get("acilis_tutar") and not d.get("acilis_tarih") and "acilis_tarih" not in self.errors:
            self.add_error("acilis_tarih", "Açılış bakiyesi için bakiye tarihini girin.")
        if d.get("acilis_tutar") is not None and d.get("acilis_tutar") <= 0 and "acilis_tutar" not in self.errors:
            self.add_error("acilis_tutar", "Açılış bakiyesi sıfırdan büyük olmalı (yön ayrıca seçilir). Bakiye yoksa boş bırakın.")
        return d

    @transaction.atomic
    def save(self, commit=True):
        cari = super().save(commit=True)
        tutar = self.cleaned_data.get("acilis_tutar")
        if tutar:                                      # boş bırakılırsa mevcut açılış kaydına dokunulmaz (kaldırmak için ekstreden iptal)
            alacak = self.cleaned_data.get("acilis_yon") == "ALACAK"
            tur = Belge.Tur.DUZELTME_EKSI if alacak else Belge.Tur.ACILIS
            aciklama = "Açılış bakiyesi" + (" (alacak / avans)" if alacak else "")
            b = self.acilis_belge
            if b is None:
                Belge.objects.create(cari=cari, tur=tur, tarih=self.cleaned_data["acilis_tarih"], tutar_kurus=tutar,
                                     aciklama=aciklama, kaynak_notu="Tedarikçi formundan girildi")
            else:
                if (b.tur, b.tutar_kurus, b.tarih) != (tur, tutar, self.cleaned_data["acilis_tarih"]):
                    b.tur, b.tutar_kurus, b.tarih = tur, tutar, self.cleaned_data["acilis_tarih"]
                    b.kdv_modu, b.kdv_orani, b.tevkifat_orani = "BILINMIYOR", None, None
                    b.matrah_kurus = b.kdv_kurus = b.tevkifat_kurus = None
                    if b.aciklama.startswith("Açılış bakiyesi"):
                        b.aciklama = aciklama
                    b.save()
        return cari

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
                if fiyat is None:
                    raise ValueError("birim fiyat girin (tutar miktar × birim fiyattan otomatik hesaplanır)")
                if fiyat <= 0:
                    raise ValueError("birim fiyat sıfırdan büyük olmalı")
                # Kalem tutarı HER ZAMAN miktar × birim fiyat'tır; formdan gelen tutar değeri yok sayılır (elle müdahale edilemez).
                tutar = int((miktar * fiyat * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                if tutar <= 0:
                    raise ValueError("hesaplanan tutar sıfırdan büyük olmalı")
                if tutar > MAKS_KURUS:
                    raise ValueError("tutar çok büyük")
                temiz.append((k["aciklama"], miktar, k["birim"][:20], fiyat, tutar))
            except ValueError as e:
                k["hata"] = str(e)
                self.add_error(None, f"Kalem {no}: {e}.")
        return temiz

    def clean(self):
        d = super().clean()
        tur, no = d.get("tur"), (d.get("evrak_no") or "").strip()
        kalemler = self._kalemleri_coz()
        if kalemler and tur not in (Belge.Tur.ALIS_FISI, Belge.Tur.ALIS_FATURASI, Belge.Tur.IADE):
            self.add_error(None, "Fiş kalemleri yalnızca alış fişi, alış faturası veya iadede girilir.")
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
            if self._diger_belgeler().filter(tur=tur, evrak_no=no).exists():
                self.add_error("evrak_no", f"Bu tedarikçide {no} numaralı {dict(Belge.Tur.choices)[tur].lower()} zaten kayıtlı.")
        if tur and d.get("tarih") and d.get("tutar_kurus") and not self.errors and not self.yinelenme:
            benzer = self._diger_belgeler().filter(tur=tur, tarih=d["tarih"])
            odenecek = self._odenecek_tutar(d)             # KDV'li girişte veritabanına yazılacak (çevrilmiş) tutar
            if any(b.tutar_kurus in (odenecek, d["tutar_kurus"]) for b in benzer) \
                    and not d.get("yine_de"):
                self.yinelenme = True
                raise forms.ValidationError(
                    "Aynı gün aynı türde aynı tutarda bir kayıt zaten var. Çift giriş olmadığından eminseniz "
                    "'Uyarıyı gördüm; yine de kaydet' kutusunu işaretleyip tekrar kaydedin.")
        return d

    def _diger_belgeler(self):
        """Çift giriş / evrak no denetimi için bu carinin aktif belgeleri (düzeltmede kayıt kendisi hariç)."""
        qs = Belge.objects.filter(cari=self.cari, iptal=False)
        return qs.exclude(pk=self.instance.pk) if self.instance.pk else qs

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

    def _kalemleri_yaz(self, belge):
        self.olusan_kalemler = []
        harita = malzeme_servisi.katla_haritasi()
        for sira, (aciklama, miktar, birim, fiyat, tutar) in enumerate(self.kalemler_temiz, start=1):
            malzeme, _ = malzeme_servisi.malzeme_bul_veya_olustur(aciklama, birim, harita)     # katalog kendiliğinden büyür
            self.olusan_kalemler.append(BelgeKalem.objects.create(
                belge=belge, malzeme=malzeme, sira=sira, aciklama=aciklama, miktar=miktar, birim=birim,
                birim_fiyat=fiyat, tutar_kurus=tutar))

    def save(self, commit=True):
        """Belge + fiş kalemleri TEK işlemde kaydedilir (biri başarısızsa hiçbiri kalmaz)."""
        with transaction.atomic():
            belge = super().save(commit=True)
            self._kalemleri_yaz(belge)
        return belge


def _sayi_metni(d) -> str:
    """Decimal('13.500') -> '13,5' (forma geri doldurmak için)."""
    if d is None:
        return ""
    return format(d.normalize(), "f").replace(".", ",")


class BelgeDuzeltForm(BelgeForm):
    """Var olan cari hareketini (fiş) düzeltir. Cari ve evrak TÜRÜ değişmez; tarih, no, açıklama, tutar, KDV ve fiş kalemleri düzelir.
    Değişiklik işlem günlüğüne eski/yeni değerle yazılır. Bakiye geriye dönük olarak yeni tutara göre hesaplanır."""

    def __init__(self, *args, belge, **kwargs):
        super().__init__(*args, instance=belge, cari=belge.cari, **kwargs)
        self.belge = belge
        self.fields["tur"].choices = [(belge.tur, belge.get_tur_display())]
        self.fields["tur"].disabled = True
        if not self.is_bound:
            self.initial["tutar_kurus"] = self._girilen_tutar(belge)
            self.kalem_satirlari = []
            for k in belge.kalemler.order_by("sira"):
                fiyat = k.birim_fiyat
                if fiyat is None and k.miktar:                       # eski kayıt (ör. Excel): fiyat yok, tutardan türet
                    fiyat = (Decimal(k.tutar_kurus) / 100 / k.miktar).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                tutar = int((k.miktar * fiyat * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)) if fiyat is not None else k.tutar_kurus
                self.kalem_satirlari.append({"aciklama": k.aciklama, "miktar": _sayi_metni(k.miktar), "birim": k.birim,
                                             "fiyat": _sayi_metni(fiyat), "tutar": kurus_bicimle(tutar)})

    @staticmethod
    def _girilen_tutar(b) -> int:
        """KDV'li kayıtta formda 'girilen' tutar gösterilir (kayıtta ödenecek tutara çevrilmişti); kaydederken yeniden çevrilir."""
        if b.kdv_modu == KdvModu.HARIC and b.matrah_kurus is not None:
            return b.matrah_kurus
        if b.kdv_modu == KdvModu.DAHIL and b.matrah_kurus is not None and b.kdv_kurus is not None:
            return b.matrah_kurus + b.kdv_kurus
        return b.tutar_kurus

    def _post_clean(self):
        # eski KDV çözümü yeni tutarla uyuşmaz: temizle, save() yeniden hesaplar
        self.instance.matrah_kurus = self.instance.kdv_kurus = self.instance.tevkifat_kurus = None
        super()._post_clean()

    def save(self, commit=True):
        with transaction.atomic():
            belge = forms.ModelForm.save(self, commit=True)
            self.olusan_kalemler = []
            mevcut = [(k.aciklama, k.miktar, k.birim, k.birim_fiyat, k.tutar_kurus) for k in belge.kalemler.order_by("sira")]
            if mevcut != self.kalemler_temiz:             # kalemler değişmediyse dokunma (günlük gürültüsü olmasın)
                belge.kalemler.all().delete()
                self._kalemleri_yaz(belge)
        return belge
