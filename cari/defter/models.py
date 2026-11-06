from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Q, Sum

from .fields import KurusField
from .kdv import KdvModu, kdv_hesapla


class KdvliTutar(models.Model):
    """KDV/tevkifat alanları. `tutar_kurus` her zaman 'ödenecek/bakiyeye etki eden' tutardır."""

    tutar_kurus = KurusField(
        "Tutar (₺)",
        help_text="KDV'li/hariç seçimine göre girin; kayıtta 'ödenecek tutar'a çevrilir.",
    )
    kdv_modu = models.CharField("KDV girişi", max_length=12, choices=KdvModu.choices,
                                default=KdvModu.BILINMIYOR)
    kdv_orani = models.DecimalField("KDV oranı (%)", max_digits=5, decimal_places=2,
                                    null=True, blank=True)
    tevkifat_orani = models.DecimalField("Tevkifat oranı (KDV'nin %)", max_digits=5,
                                         decimal_places=2, null=True, blank=True)
    matrah_kurus = KurusField("Matrah (₺)", null=True, blank=True, editable=False)
    kdv_kurus = KurusField("KDV (₺)", null=True, blank=True, editable=False)
    tevkifat_kurus = KurusField("Tevkifat (₺)", null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def _kdv_bekliyor(self) -> bool:
        return (self.kdv_modu in (KdvModu.HARIC, KdvModu.DAHIL)
                and self.kdv_orani is not None and self.matrah_kurus is None)

    def efektif_tutar_kurus(self) -> int:
        """Kayıttan sonra bakiyeye etki edecek tutar (KDV henüz çözülmediyse önizleme)."""
        if self.tutar_kurus is None:
            return 0
        if self._kdv_bekliyor():
            return kdv_hesapla(self.tutar_kurus, self.kdv_orani, self.kdv_modu,
                               self.tevkifat_orani)["odenecek_kurus"]
        return self.tutar_kurus

    def kdv_coz(self):
        if self._kdv_bekliyor():
            h = kdv_hesapla(self.tutar_kurus, self.kdv_orani, self.kdv_modu, self.tevkifat_orani)
            self.matrah_kurus = h["matrah_kurus"]
            self.kdv_kurus = h["kdv_kurus"]
            self.tevkifat_kurus = h["tevkifat_kurus"] or None
            self.tutar_kurus = h["odenecek_kurus"]

    def clean_kdv(self):
        if self.kdv_modu != KdvModu.BILINMIYOR and self.kdv_orani is None:
            raise ValidationError({"kdv_orani": "KDV girişi seçildiyse KDV oranı da girilmeli."})
        if self.tevkifat_orani and self.kdv_modu != KdvModu.HARIC:
            raise ValidationError({"tevkifat_orani": "Tevkifat yalnızca 'KDV hariç' girişte kullanılır."})
        if self.matrah_kurus is not None and self.kdv_kurus is not None:
            beklenen = self.matrah_kurus + self.kdv_kurus - (self.tevkifat_kurus or 0)
            if beklenen != self.tutar_kurus:
                raise ValidationError(
                    "Tutar, matrah + KDV − tevkifat ile uyuşmuyor. "
                    "KDV alanlarını yeniden hesaplamak için KDV girişini 'bilinmiyor' yapıp tutarı düzeltin.")

    def save(self, *args, **kwargs):
        self.kdv_coz()
        super().save(*args, **kwargs)


class Cari(models.Model):
    class Tur(models.TextChoices):
        TEDARIKCI = "TEDARIKCI", "Tedarikçi"

    tur = models.CharField("Tür", max_length=12, choices=Tur.choices, default=Tur.TEDARIKCI)
    unvan = models.CharField("Ünvan", max_length=200, unique=True)
    kisa_kod = models.CharField("Kısa kod", max_length=30, blank=True)
    tedarikcideki_kodumuz = models.CharField("Tedarikçideki cari kodumuz", max_length=50, blank=True)
    vergi_bilgisi = models.CharField("Vergi dairesi / no", max_length=100, blank=True)
    telefon = models.CharField(max_length=50, blank=True)
    eposta = models.CharField("E-posta", max_length=120, blank=True)
    yetkili = models.CharField(max_length=100, blank=True)
    vade_gun = models.PositiveIntegerField("Ödeme vadesi (gün)", null=True, blank=True)
    not_metni = models.TextField("Not", blank=True)
    aktif = models.BooleanField(default=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cari"
        verbose_name_plural = "Cariler"
        ordering = ["unvan"]

    def __str__(self):
        return self.unvan

    def bakiye_kurus(self) -> int:
        from .services import bakiye_kurus
        return bakiye_kurus(self)


class Belge(KdvliTutar):
    class Tur(models.TextChoices):
        ACILIS = "ACILIS", "Açılış / Devir"
        ALIS_FISI = "ALIS_FISI", "Alış Fişi"
        ALIS_FATURASI = "ALIS_FATURASI", "Alış Faturası"
        IADE = "IADE", "İade"
        ODEME = "ODEME", "Ödeme"
        DUZELTME_ARTI = "DUZELTME_ARTI", "Düzeltme (+)"
        DUZELTME_EKSI = "DUZELTME_EKSI", "Düzeltme (−)"

    class OdemeSekli(models.TextChoices):
        HAVALE = "HAVALE", "Havale/EFT"
        NAKIT = "NAKIT", "Nakit"
        KREDI_KARTI = "KREDI_KARTI", "Kredi Kartı"
        CEK = "CEK", "Çek"
        SENET = "SENET", "Senet"
        MAHSUP = "MAHSUP", "Mahsup"

    # Borcu artıran / azaltan türler (Excel'deki gizli "Listeler" sayfasının karşılığı)
    ARTIRAN = (Tur.ACILIS, Tur.ALIS_FISI, Tur.ALIS_FATURASI, Tur.DUZELTME_ARTI)
    AZALTAN = (Tur.IADE, Tur.ODEME, Tur.DUZELTME_EKSI)

    cari = models.ForeignKey(Cari, on_delete=models.PROTECT, related_name="belgeler",
                             verbose_name="Cari")
    tur = models.CharField("Evrak türü", max_length=14, choices=Tur.choices)
    tarih = models.DateField()
    evrak_no = models.CharField("Evrak / fiş no", max_length=40, blank=True)
    harici_evrak_no = models.CharField("Tedarikçi evrak no", max_length=40, blank=True)
    aciklama = models.CharField("Açıklama", max_length=250, blank=True)
    odeme_sekli = models.CharField("Ödeme şekli", max_length=12, choices=OdemeSekli.choices,
                                   blank=True)
    kaynak_notu = models.CharField("Kaynak / not", max_length=250, blank=True)
    iptal = models.BooleanField("İptal", default=False)
    iptal_nedeni = models.CharField("İptal nedeni", max_length=250, blank=True)
    olusturma = models.DateTimeField(auto_now_add=True)
    guncelleme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cari hareket (belge)"
        verbose_name_plural = "Cari hareketler (belgeler)"
        ordering = ["tarih", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(tutar_kurus__gt=0), name="belge_tutar_pozitif"),
            models.UniqueConstraint(
                fields=["cari", "tur", "evrak_no"],
                condition=~Q(evrak_no="") & Q(iptal=False),
                name="belge_evrak_no_tekil",
            ),
        ]
        indexes = [models.Index(fields=["cari", "tarih"])]

    def __str__(self):
        return f"{self.get_tur_display()} · {self.cari} · {self.tarih:%d.%m.%Y}"

    @property
    def etki(self) -> int:
        return 1 if self.tur in self.ARTIRAN else -1

    def clean(self):
        if self.tutar_kurus is not None and self.tutar_kurus <= 0:
            raise ValidationError({"tutar_kurus": "Tutar sıfırdan büyük olmalı. Yön, evrak türünden gelir."})
        if self.iptal and not self.iptal_nedeni:
            raise ValidationError({"iptal_nedeni": "İptal için neden yazın."})
        self.clean_kdv()


class BelgeKalem(models.Model):
    belge = models.ForeignKey(Belge, on_delete=models.CASCADE, related_name="kalemler")
    sira = models.PositiveIntegerField("Sıra", default=1)
    stok_kodu = models.CharField(max_length=60, blank=True)
    aciklama = models.CharField("Açıklama", max_length=250)
    miktar = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    birim = models.CharField(max_length=20, blank=True)
    birim_fiyat = models.DecimalField("Birim fiyat", max_digits=16, decimal_places=4,
                                      null=True, blank=True)
    tutar_kurus = KurusField("Tutar (₺)")

    class Meta:
        verbose_name = "Kalem"
        verbose_name_plural = "Kalemler"
        ordering = ["belge", "sira"]

    def __str__(self):
        return f"{self.belge_id}/{self.sira} {self.aciklama}"


class Hesap(models.Model):
    class Tur(models.TextChoices):
        KASA = "KASA", "Kasa"
        BANKA = "BANKA", "Banka"

    ad = models.CharField(max_length=80, unique=True)
    tur = models.CharField(max_length=6, choices=Tur.choices, default=Tur.KASA)
    acilis_bakiye_kurus = KurusField("Açılış bakiyesi (₺)", default=0)
    eksiye_dusebilir = models.BooleanField("Bakiye eksiye düşebilir", default=False)
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Hesap (kasa)"
        verbose_name_plural = "Hesaplar (kasa)"
        ordering = ["ad"]

    def __str__(self):
        return self.ad

    def kilit_siniri(self):
        """Gün sonu kapanışı yapılmış en son tarih (bu tarihe ve öncesine kayıt girilemez)."""
        return self.gun_sonlari.filter(kilitli=True).aggregate(m=Max("tarih"))["m"]

    def bakiye_kurus(self, haric_hareket_id=None, tarih_kadar=None) -> int:
        qs = self.hareketler.filter(iptal=False)
        if haric_hareket_id:
            qs = qs.exclude(pk=haric_hareket_id)
        if tarih_kadar:
            qs = qs.filter(tarih__lte=tarih_kadar)
        giris = qs.filter(yon=KasaHareketi.Yon.GIRIS).aggregate(t=Sum("tutar_kurus"))["t"] or 0
        cikis = qs.filter(yon=KasaHareketi.Yon.CIKIS).aggregate(t=Sum("tutar_kurus"))["t"] or 0
        return self.acilis_bakiye_kurus + giris - cikis


class KasaKategori(models.Model):
    class Tur(models.TextChoices):
        GELIR = "GELIR", "Gelir"
        GIDER = "GIDER", "Gider"

    ad = models.CharField(max_length=80, unique=True)
    tur = models.CharField(max_length=5, choices=Tur.choices, default=Tur.GIDER)
    genel_gider_grubu = models.CharField("Genel gider grubu", max_length=80, blank=True)
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kasa kategorisi"
        verbose_name_plural = "Kasa kategorileri"
        ordering = ["ad"]

    def __str__(self):
        return self.ad


class KasaHareketi(KdvliTutar):
    """Kasa hareketi cari ödemesinden BAĞIMSIZDIR; ilgili ödeme alanı yalnızca isteğe bağlı referanstır."""

    class Yon(models.TextChoices):
        GIRIS = "GIRIS", "Giriş"
        CIKIS = "CIKIS", "Çıkış"

    hesap = models.ForeignKey(Hesap, on_delete=models.PROTECT, related_name="hareketler")
    tarih = models.DateField()
    yon = models.CharField("Yön", max_length=5, choices=Yon.choices)
    kategori = models.ForeignKey(KasaKategori, null=True, blank=True, on_delete=models.PROTECT)
    cari = models.ForeignKey(Cari, null=True, blank=True, on_delete=models.PROTECT,
                             related_name="kasa_hareketleri")
    ilgili_odeme = models.ForeignKey(
        Belge, null=True, blank=True, on_delete=models.PROTECT, related_name="kasa_hareketleri",
        limit_choices_to={"tur": Belge.Tur.ODEME}, verbose_name="İlgili cari ödemesi (isteğe bağlı)")
    makbuz_no = models.CharField("Makbuz / fiş no", max_length=40, blank=True)
    aciklama = models.CharField("Açıklama", max_length=250, blank=True)
    iptal = models.BooleanField("İptal", default=False)
    iptal_nedeni = models.CharField("İptal nedeni", max_length=250, blank=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kasa hareketi"
        verbose_name_plural = "Kasa hareketleri"
        ordering = ["tarih", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(tutar_kurus__gt=0), name="kasa_tutar_pozitif"),
        ]

    def __str__(self):
        return f"{self.hesap} · {self.get_yon_display()} · {self.tarih:%d.%m.%Y}"

    def kilit_kontrol(self):
        """Kapatılmış güne kayıt eklenemez; kapatılmış güne ait kayıt değiştirilemez/iptal edilemez."""
        if not self.hesap_id:
            return
        sinir = self.hesap.kilit_siniri()
        if not sinir:
            return
        if self.pk:
            eski = KasaHareketi.objects.filter(pk=self.pk).values_list("tarih", flat=True).first()
            if eski and eski <= sinir:
                raise ValidationError(
                    "Bu kayıt kapatılmış bir güne ait; değiştirilemez veya iptal edilemez. "
                    "Düzeltme için güncel tarihli bir ters kayıt girin.")
        if self.tarih and self.tarih <= sinir:
            raise ValidationError({"tarih": (
                f"Kasa {sinir:%d.%m.%Y} tarihine kadar kapatıldı; bu tarihe kayıt girilemez. "
                "Düzeltme için güncel tarihli bir ters kayıt girin.")})

    def save(self, *args, **kwargs):
        self.kilit_kontrol()
        super().save(*args, **kwargs)

    def clean(self):
        if self.tutar_kurus is not None and self.tutar_kurus <= 0:
            raise ValidationError({"tutar_kurus": "Tutar sıfırdan büyük olmalı. Yön ayrı seçilir."})
        if self.iptal and not self.iptal_nedeni:
            raise ValidationError({"iptal_nedeni": "İptal için neden yazın."})
        self.clean_kdv()
        self.kilit_kontrol()
        if (self.iptal and self.pk and self.yon == self.Yon.GIRIS and not self.hesap.eksiye_dusebilir
                and KasaHareketi.objects.filter(pk=self.pk, iptal=False).exists()
                and self.hesap.bakiye_kurus(haric_hareket_id=self.pk) < 0):
            raise ValidationError("Bu girişi iptal etmek kasa bakiyesini eksiye düşürür.")
        if (self.hesap_id and self.tutar_kurus and not self.iptal
                and self.yon == self.Yon.CIKIS and not self.hesap.eksiye_dusebilir):
            mevcut = self.hesap.bakiye_kurus(haric_hareket_id=self.pk)
            if mevcut - self.efektif_tutar_kurus() < 0:
                raise ValidationError("Bu çıkış kasa bakiyesini eksiye düşürür.")


class EkstreMutabakat(models.Model):
    """Tedarikçinin gönderdiği ekstre ile bizim kayıtlarımızın karşılaştırması."""

    cari = models.ForeignKey(Cari, on_delete=models.PROTECT, related_name="mutabakatlar")
    ekstre_tarihi = models.DateField("Ekstre tarihi")
    ekstre_bakiye_kurus = KurusField("Ekstredeki bakiye (₺)",
                                     help_text="Tedarikçi ekstresine göre bizim borcumuz.")
    aciklama = models.CharField("Açıklama", max_length=250, blank=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ekstre mutabakatı"
        verbose_name_plural = "Ekstre mutabakatları"
        ordering = ["-ekstre_tarihi", "cari"]
        constraints = [
            models.UniqueConstraint(fields=["cari", "ekstre_tarihi"], name="mutabakat_tekil"),
        ]

    def __str__(self):
        return f"{self.cari} · ekstre {self.ekstre_tarihi:%d.%m.%Y}"


class EkstreSatiri(models.Model):
    class Durum(models.TextChoices):
        UYUMLU = "UYUMLU", "Uyumlu"
        FARKLI = "FARKLI", "Tutar farkı"
        EKSTREDE_YOK = "EKSTREDE_YOK", "Ekstrede yok"
        BIZDE_YOK = "BIZDE_YOK", "Bizde yok"

    mutabakat = models.ForeignKey(EkstreMutabakat, on_delete=models.CASCADE, related_name="satirlar")
    sira = models.PositiveIntegerField("Sıra", default=1)
    belge = models.ForeignKey(Belge, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="ekstre_satirlari", verbose_name="Bizim kayıt")
    tarih = models.DateField(null=True, blank=True)
    tur_metni = models.CharField("Tür", max_length=30, blank=True)
    ekstre_evrak_no = models.CharField("Ekstre evrak no", max_length=40, blank=True)
    ekstre_tutar_kurus = KurusField("Ekstre tutarı (₺)", null=True, blank=True)
    aciklama = models.CharField("Açıklama / neden", max_length=300, blank=True)

    class Meta:
        verbose_name = "Ekstre satırı"
        verbose_name_plural = "Ekstre satırları"
        ordering = ["mutabakat", "sira"]

    @property
    def bizim_tutar_kurus(self):
        return self.belge.tutar_kurus if self.belge_id and not self.belge.iptal else None

    @property
    def fark_kurus(self) -> int:
        """Bizim tutar − ekstre tutarı. Pozitif: bizde daha yüksek."""
        return (self.bizim_tutar_kurus or 0) - (self.ekstre_tutar_kurus or 0)

    @property
    def etki(self) -> int:
        return self.belge.etki if self.belge_id else 1

    @property
    def bakiye_farki_kurus(self) -> int:
        """Bu satırın, bakiye farkına (bizim − ekstre) katkısı."""
        return self.etki * self.fark_kurus

    @property
    def durum(self) -> str:
        bizim, ekstre = self.bizim_tutar_kurus, self.ekstre_tutar_kurus
        if bizim is None and ekstre is None:
            return self.Durum.UYUMLU
        if ekstre is None:
            return self.Durum.EKSTREDE_YOK
        if bizim is None:
            return self.Durum.BIZDE_YOK
        return self.Durum.UYUMLU if bizim == ekstre else self.Durum.FARKLI

    @property
    def durum_etiketi(self) -> str:
        return self.Durum(self.durum).label


class GunSonu(models.Model):
    """Gün sonu kasa kapanışı: sayılan nakit ile kayıtlı bakiyenin karşılaştırması. Kilitler."""

    hesap = models.ForeignKey(Hesap, on_delete=models.PROTECT, related_name="gun_sonlari")
    tarih = models.DateField("Kapanış günü")
    beklenen_kurus = KurusField("Kayıtlara göre bakiye (₺)")
    sayilan_kurus = KurusField("Sayılan nakit (₺)")
    fark_kurus = KurusField("Fark (₺)", help_text="Sayılan − beklenen. Pozitif: kasa fazlası, negatif: kasa noksanı.")
    fark_islendi = models.BooleanField("Fark kasa hareketi olarak işlendi", default=False)
    aciklama = models.CharField("Açıklama", max_length=250, blank=True)
    kilitli = models.BooleanField("Kilitli", default=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gün sonu kapanışı"
        verbose_name_plural = "Gün sonu kapanışları"
        ordering = ["-tarih"]
        constraints = [
            models.UniqueConstraint(fields=["hesap", "tarih"], name="gun_sonu_tekil"),
        ]

    def __str__(self):
        return f"{self.hesap} · {self.tarih:%d.%m.%Y}"
