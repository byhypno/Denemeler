from datetime import date
from io import BytesIO

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from . import kasa_servisi as ks
from .models import GenelGider, GiderKategori, Hesap, IslemGunlugu, KasaHareketi, KasaKategori
from .test_yardimci import rol_kullanici

GIRIS, CIKIS = KasaHareketi.Yon.GIRIS, KasaHareketi.Yon.CIKIS


class Temel(TestCase):
    def setUp(self):
        self.kasa = Hesap.objects.get(ad="Ofis Kasa")
        self.kat = KasaKategori.objects.create(ad="Kırtasiye")
        self.h1 = self.yeni(CIKIS, 1000, date(2026, 5, 1), harcayan="ali", aciklama="Çay ve şeker", makbuz_no="A1", kategori=self.kat)
        self.h2 = self.yeni(CIKIS, 2500, date(2026, 5, 2), harcayan="ALİ", aciklama="Kargo")
        self.h3 = self.yeni(CIKIS, 300, date(2026, 5, 3), harcayan="", aciklama="Pil")
        self.h4 = self.yeni(GIRIS, 10000, date(2026, 5, 3), harcayan="Veli")
        self.h5 = self.yeni(CIKIS, 777, date(2026, 5, 4), harcayan="Veli", iptal=True, iptal_nedeni="hata")

    def yeni(self, yon, tutar, tarih, **kw):
        return KasaHareketi.objects.create(hesap=self.kasa, yon=yon, tutar_kurus=tutar, tarih=tarih, **kw)

    def giris(self, rol="Muhasebe"):
        u = rol_kullanici("k_" + rol, rol)
        self.client.force_login(u)
        return u


class ListeSuzgecTests(Temel):
    def sorgu(self, **kw):
        return ks.hareket_sorgusu(self.kasa, kw)[0]

    def test_metin_arama_aksan_ve_buyuk_kucuk_harf_yok_sayar(self):
        self.assertEqual(list(self.sorgu(q="CAY SEKER")), [self.h1])      # Çay -> cay, şeker -> seker
        self.assertEqual(list(self.sorgu(q="kirtasiye")), [self.h1])      # kategori adında
        self.assertEqual(list(self.sorgu(q="a1")), [self.h1])             # makbuz

    def test_harcayan_filtresi_yazim_farkini_birlestirir(self):
        self.assertEqual({h.pk for h in self.sorgu(harcayan="Ali")}, {self.h1.pk, self.h2.pk})
        self.assertEqual(list(self.sorgu(harcayan="-")), [self.h3])

    def test_toplam_iptali_saymaz(self):
        t = ks.sorgu_toplami(self.sorgu(iptal="1"))
        self.assertEqual((t["giris"], t["cikis"], t["net"], t["adet"]), (10000, 3800, 6200, 4))

    def test_ekran_ve_excel(self):
        self.giris()
        r = self.client.get(reverse("kasa"), {"q": "kargo"})
        self.assertContains(r, "Kargo")
        self.assertContains(r, "1 kayıt")          # yalnızca Kargo süzüldü
        self.assertContains(r, "Bu listeyi Excel")
        r = self.client.get(reverse("kasa"), {"harcayan": "ali", "indir": "xlsx"})
        ws = load_workbook(BytesIO(r.content)).active
        self.assertEqual([c.value for c in ws["E"]][1:], ["Çay ve şeker", "Kargo"])
        self.assertEqual(float(ws["G2"].value), 10.0)

    def test_excel_formul_enjeksiyonu_olmaz(self):
        self.yeni(CIKIS, 100, date(2026, 5, 5), aciklama="=1+1")
        self.giris()
        r = self.client.get(reverse("kasa"), {"q": "1+1", "indir": "xlsx"})
        h = load_workbook(BytesIO(r.content)).active["E2"]
        self.assertEqual((h.data_type, h.value), ("s", "=1+1"))


class HarcayanDuzeltTests(Temel):
    def test_yazim_farki_birlestirilir_bakiye_ve_gunluk(self):
        onceki = self.kasa.bakiye_kurus()
        n = IslemGunlugu.objects.count()
        s = ks.harcayan_duzelt(self.kasa, "ali", "Ali")
        self.assertEqual(s, {"degisen": 2, "kilitli": 0})
        self.h1.refresh_from_db(); self.h2.refresh_from_db()
        self.assertEqual((self.h1.harcayan, self.h2.harcayan), ("Ali", "Ali"))
        self.assertEqual(self.kasa.bakiye_kurus(), onceki)
        self.assertEqual(IslemGunlugu.objects.count(), n + 2)

    def test_bos_harcayan_doldurulur_iptale_dokunulmaz(self):
        self.yeni(CIKIS, 5, date(2026, 5, 6), harcayan="", iptal=True, iptal_nedeni="x")
        s = ks.harcayan_duzelt(self.kasa, "-", "Ofis")
        self.assertEqual(s["degisen"], 1)
        self.h3.refresh_from_db()
        self.assertEqual(self.h3.harcayan, "Ofis")

    def test_kapali_gun_atlanir(self):
        from .models import GunSonu
        GunSonu.objects.create(hesap=self.kasa, tarih=date(2026, 5, 1), beklenen_kurus=0, sayilan_kurus=0, fark_kurus=0, kilitli=True)
        s = ks.harcayan_duzelt(self.kasa, "ali", "Ali")
        self.assertEqual(s, {"degisen": 1, "kilitli": 1})
        self.h1.refresh_from_db()
        self.assertEqual(self.h1.harcayan, "ali")

    def test_bos_yeni_ad_reddedilir(self):
        with self.assertRaises(ValidationError):
            ks.harcayan_duzelt(self.kasa, "ali", "  ")

    def test_yetki_ve_gorunum(self):
        self.giris("Görüntüleyici")
        self.assertEqual(self.client.get(reverse("kasa_harcayan_duzelt")).status_code, 403)
        self.assertEqual(self.client.post(reverse("kasa_harcayan_duzelt"), {"eski": "ali", "yeni": "Ali"}).status_code, 403)
        self.client.logout()
        self.giris("Kasiyer")
        self.assertContains(self.client.get(reverse("kasa_harcayan_duzelt")), "Harcayan adlarını düzelt")
        r = self.client.post(reverse("kasa_harcayan_duzelt"), {"hesap": self.kasa.pk, "eski": "ali", "yeni": "Ali"}, follow=True)
        self.assertContains(r, "2 kayıtta harcayan düzeltildi")
        self.assertEqual(KasaHareketi.objects.filter(harcayan="Ali").count(), 2)


class GenelBakisGostergeTests(Temel):
    def test_kasa_bakiyesi_ve_ay_gideri(self):
        from datetime import date as d
        bugun = d.today()
        kat = GiderKategori.objects.first() or GiderKategori.objects.create(ad="Kira")
        GenelGider.objects.create(yil=bugun.year, ay=bugun.month, kategori=kat, tutar_kurus=1250000)
        from .models import Cari, Belge
        c = Cari.objects.create(unvan="X")
        Belge.objects.create(cari=c, tur=Belge.Tur.ALIS_FISI, tarih=bugun, tutar_kurus=100)
        self.giris("Muhasebe")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Ofis Kasa bakiyesi")
        self.assertContains(r, "12.500,00")
        self.assertContains(r, "net genel gider")
