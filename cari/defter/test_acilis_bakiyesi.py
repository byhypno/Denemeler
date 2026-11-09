"""Tedarikçi oluştururken açılış bakiyesi."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from .models import Belge, Cari, IslemGunlugu
from .test_yardimci import rol_kullanici


class AcilisBakiyesiTests(TestCase):
    def setUp(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.url = reverse("tedarikci_yeni")

    def post(self, **kw):
        d = {"unvan": "YENİ TEDARİKÇİ", "acilis_tutar": "", "acilis_yon": "BORC", "acilis_tarih": "2026-11-01"}
        d.update(kw)
        return self.client.post(self.url, d)

    def test_form_alanlari_gorunur_tarih_bugun(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Açılış bakiyesi (₺)")
        self.assertContains(r, "Tedarikçiye borcumuz var")
        self.assertContains(r, f'value="{date.today():%Y-%m-%d}"')

    def test_borc_acilisi_bakiye_olarak_gorunur(self):
        r = self.post(acilis_tutar="12.345,50")
        self.assertEqual(r.status_code, 302)
        c = Cari.objects.get()
        b = c.belgeler.get()
        self.assertEqual((b.tur, b.tutar_kurus, b.tarih, b.aciklama), ("ACILIS", 1234550, date(2026, 11, 1), "Açılış bakiyesi"))
        self.assertEqual(c.bakiye_kurus(), 1234550)

    def test_alacak_avans_acilisi_bakiyeyi_eksi_yapar(self):
        self.post(acilis_tutar="500,00", acilis_yon="ALACAK")
        c = Cari.objects.get()
        self.assertEqual(c.bakiye_kurus(), -50000)
        self.assertIn("avans", c.belgeler.get().aciklama)

    def test_bos_ise_belge_olusmaz(self):
        self.post()
        self.assertEqual((Cari.objects.count(), Belge.objects.count()), (1, 0))

    def test_tarihsiz_veya_gecersiz_tutar_hicbir_sey_kaydetmez(self):
        for kw, parca in (({"acilis_tutar": "100,00", "acilis_tarih": ""}, "bakiye tarihini girin"),
                          ({"acilis_tutar": "100,00", "acilis_tarih": "1999-01-01"}, "2000–2100"),
                          ({"acilis_tutar": "abc"}, "biçiminde girin"),
                          ({"acilis_tutar": "0"}, "sıfırdan büyük")):
            r = self.post(**kw)
            self.assertEqual(r.status_code, 200, kw)
            self.assertContains(r, parca)
        self.assertEqual((Cari.objects.count(), Belge.objects.count()), (0, 0))

    def test_ayni_unvan_hatasi_belge_olusturmaz(self):
        Cari.objects.create(unvan="YENİ TEDARİKÇİ")
        r = self.post(acilis_tutar="100,00")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Belge.objects.count(), 0)

    def test_duzenlemede_alanlar_yok_ve_belge_olusmaz(self):
        c = Cari.objects.create(unvan="X")
        url = reverse("tedarikci_duzenle", args=[c.pk])
        self.assertNotContains(self.client.get(url), "Açılış bakiyesi")
        self.client.post(url, {"unvan": "X", "aktif": "on", "acilis_tutar": "999,00", "acilis_tarih": "2026-11-01", "acilis_yon": "BORC"})
        self.assertEqual(Belge.objects.count(), 0)

    def test_gunluge_yazilir_ve_ekstrede_gorunur(self):
        self.post(acilis_tutar="100,00")
        self.assertTrue(IslemGunlugu.objects.filter(model="Belge", islem="OLUSTURDU").exists())
        c = Cari.objects.get()
        self.assertContains(self.client.get(reverse("cari_ekstre", args=[c.pk])), "Açılış bakiyesi")

    def test_yetki(self):
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        self.assertEqual(self.post(acilis_tutar="100,00").status_code, 403)
        self.assertEqual(Belge.objects.count(), 0)
