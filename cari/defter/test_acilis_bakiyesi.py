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

    def duzenle(self, c, **kw):
        d = {"unvan": c.unvan, "aktif": "on", "acilis_tutar": "", "acilis_yon": "BORC", "acilis_tarih": "2026-11-01"}
        d.update(kw)
        return self.client.post(reverse("tedarikci_duzenle", args=[c.pk]), d)

    def test_eski_tedarikciye_acilis_eklenir(self):
        c = Cari.objects.create(unvan="ESKİ")
        self.assertContains(self.client.get(reverse("tedarikci_duzenle", args=[c.pk])), "henüz açılış kaydı yok")
        self.assertEqual(self.duzenle(c, acilis_tutar="750,00").status_code, 302)
        self.assertEqual((c.belgeler.count(), c.bakiye_kurus()), (1, 75000))

    def test_mevcut_acilis_formda_dolu_gelir_ve_duzelir(self):
        self.post(acilis_tutar="1.000,00")
        c = Cari.objects.get()
        r = self.client.get(reverse("tedarikci_duzenle", args=[c.pk]))
        self.assertContains(r, 'value="1.000,00"')
        self.assertContains(r, "açılış kaydı var")
        self.assertEqual(self.duzenle(c, acilis_tutar="1.500,00", acilis_tarih="2026-10-01").status_code, 302)
        b = c.belgeler.get()                                                    # çoğalmadı, aynı kayıt güncellendi
        self.assertEqual((b.tutar_kurus, b.tarih), (150000, date(2026, 10, 1)))
        self.assertEqual(c.bakiye_kurus(), 150000)

    def test_yon_degisince_tur_degisir(self):
        self.post(acilis_tutar="200,00")
        c = Cari.objects.get()
        self.duzenle(c, acilis_tutar="200,00", acilis_yon="ALACAK")
        self.assertEqual((c.belgeler.get().tur, c.bakiye_kurus()), ("DUZELTME_EKSI", -20000))
        self.duzenle(c, acilis_tutar="200,00", acilis_yon="BORC")
        self.assertEqual((c.belgeler.get().tur, c.bakiye_kurus()), ("ACILIS", 20000))

    def test_bos_birakilirsa_mevcut_acilis_degismez(self):
        self.post(acilis_tutar="300,00")
        c = Cari.objects.get()
        self.duzenle(c, unvan="YENİ AD")
        self.assertEqual((c.belgeler.get().tutar_kurus, Cari.objects.get().unvan), (30000, "YENİ AD"))

    def test_excel_devri_acilis_sayilir_iptal_edilen_sayilmaz(self):
        c = Cari.objects.create(unvan="DEVİRLİ")
        d = Belge.objects.create(cari=c, tur="ACILIS", tarih=date(2026, 1, 1), tutar_kurus=10000)
        self.assertContains(self.client.get(reverse("tedarikci_duzenle", args=[c.pk])), 'value="100,00"')
        self.duzenle(c, acilis_tutar="250,00")
        d.refresh_from_db()
        self.assertEqual(d.tutar_kurus, 25000)
        Belge.objects.filter(pk=d.pk).update(iptal=True, iptal_nedeni="x")
        self.duzenle(c, acilis_tutar="90,00")                                   # iptal edilmiş açılış sayılmaz: yenisi eklenir
        self.assertEqual(c.belgeler.filter(iptal=False).count(), 1)
        self.assertEqual(c.bakiye_kurus(), 9000)

    def test_kdvli_acilis_degisince_kdv_temizlenir(self):
        c = Cari.objects.create(unvan="K")
        Belge.objects.create(cari=c, tur="ACILIS", tarih=date(2026, 1, 1), tutar_kurus=10000, kdv_modu="HARIC", kdv_orani=20)
        self.duzenle(c, acilis_tutar="500,00")
        b = c.belgeler.get()
        self.assertEqual((b.tutar_kurus, b.kdv_modu, b.matrah_kurus), (50000, "BILINMIYOR", None))

    def test_gunluge_yazilir_ve_ekstrede_gorunur(self):
        self.post(acilis_tutar="100,00")
        self.assertTrue(IslemGunlugu.objects.filter(model="Belge", islem="OLUSTURDU").exists())
        c = Cari.objects.get()
        self.assertContains(self.client.get(reverse("cari_ekstre", args=[c.pk])), "Açılış bakiyesi")

    def test_yetki(self):
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        self.assertEqual(self.post(acilis_tutar="100,00").status_code, 403)
        self.assertEqual(Belge.objects.count(), 0)
