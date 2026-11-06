"""Arayüzden cari hareket girişi ve iptali (alış fişi/faturası, ödeme, iade, düzeltme)."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from .models import Belge, Cari, IslemGunlugu
from .test_yardimci import rol_kullanici


class Temel(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="Giriş Tedarik", vade_gun=30)
        self.url = reverse("belge_yeni", args=[self.cari.pk])
        self.muh = rol_kullanici("m", "Muhasebe")
        self.client.force_login(self.muh)

    def veri(self, **kw):
        d = {"tur": "ALIS_FISI", "tarih": "2026-03-05", "tutar_kurus": "1.250,50", "kdv_modu": "BILINMIYOR"}
        d.update(kw)
        return d


class GirisTests(Temel):
    def test_form_acilir_turu_onceden_secer(self):
        r = self.client.get(self.url, {"tur": "ODEME"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Giriş Tedarik")
        self.assertContains(r, '<option value="ODEME" selected>')
        self.assertNotContains(r, "Açılış")                       # devir yalnızca yönetim panelinden
        self.assertEqual(r.content.decode().count("<h1"), 1)
        self.assertContains(self.client.get(self.url, {"tur": "ACILIS"}), '<option value="ALIS_FISI" selected>')   # geçersiz tür: varsayılan

    def test_alis_fisi_kaydedilir_ve_ekstreye_doner(self):
        r = self.client.post(self.url, self.veri(evrak_no="101", aciklama="vida"))
        self.assertRedirects(r, reverse("cari_ekstre", args=[self.cari.pk]))
        b = Belge.objects.get()
        self.assertEqual((b.cari, b.tur, b.tutar_kurus, b.evrak_no, b.aciklama), (self.cari, "ALIS_FISI", 125050, "101", "vida"))
        self.assertEqual(self.cari.bakiye_kurus(), 125050)

    def test_odeme_bakiyeyi_dusurur_ve_odeme_sekli_yalniz_odemede(self):
        self.client.post(self.url, self.veri(tur="ALIS_FISI", tutar_kurus="2.000,00", odeme_sekli="NAKIT", evrak_no="1"))
        self.client.post(self.url, self.veri(tur="ODEME", tutar_kurus="500,00", odeme_sekli="HAVALE"))
        alis, odeme = Belge.objects.order_by("id")
        self.assertEqual(alis.odeme_sekli, "")                    # alışta ödeme şekli temizlenir
        self.assertEqual(odeme.odeme_sekli, "HAVALE")
        self.assertEqual(self.cari.bakiye_kurus(), 150000)

    def test_iade_ve_duzeltme_yonleri(self):
        self.client.post(self.url, self.veri(tutar_kurus="1.000,00", evrak_no="1"))
        self.client.post(self.url, self.veri(tur="IADE", tutar_kurus="100,00"))
        self.client.post(self.url, self.veri(tur="DUZELTME_EKSI", tutar_kurus="50,00"))
        self.client.post(self.url, self.veri(tur="DUZELTME_ARTI", tutar_kurus="20,00"))
        self.assertEqual(self.cari.bakiye_kurus(), 100000 - 10000 - 5000 + 2000)

    def test_kdv_haric_tutar_odenecege_cevrilir(self):
        self.client.post(self.url, self.veri(tutar_kurus="1.000,00", kdv_modu="HARIC", kdv_orani="20", evrak_no="7"))
        b = Belge.objects.get()
        self.assertEqual((b.matrah_kurus, b.kdv_kurus, b.tutar_kurus), (100000, 20000, 120000))

    def test_kdv_hatalari(self):
        r = self.client.post(self.url, self.veri(kdv_modu="HARIC"))                    # oran yok
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "KDV oranı da girilmeli")
        r = self.client.post(self.url, self.veri(kdv_modu="DAHIL", kdv_orani="20", tevkifat_orani="50"))
        self.assertContains(r, "Tevkifat yalnızca")
        self.assertEqual(Belge.objects.count(), 0)

    def test_gecersiz_girisler_kaydedilmez(self):
        for kw in ({"tutar_kurus": "1234.50"}, {"tutar_kurus": "0,00"}, {"tutar_kurus": ""}, {"tutar_kurus": "-5,00"},
                   {"tarih": ""}, {"tarih": "31.02.2026"}, {"tur": "ACILIS"}, {"tur": "SACMA"}):
            r = self.client.post(self.url, self.veri(**kw))
            self.assertEqual(r.status_code, 200, kw)
        self.assertEqual(Belge.objects.count(), 0)

    def test_ayni_evrak_no_reddedilir_iptal_sonrasi_serbest(self):
        self.client.post(self.url, self.veri(evrak_no="55"))
        r = self.client.post(self.url, self.veri(evrak_no="55", tutar_kurus="9,00"))
        self.assertContains(r, "zaten kayıtlı")
        self.assertEqual(Belge.objects.count(), 1)
        b = Belge.objects.get()
        b.iptal, b.iptal_nedeni = True, "x"
        b.save()
        self.assertEqual(self.client.post(self.url, self.veri(evrak_no="55", tutar_kurus="9,00")).status_code, 302)
        # farklı tür veya farklı tedarikçide aynı numara serbest
        self.assertEqual(self.client.post(self.url, self.veri(tur="ALIS_FATURASI", evrak_no="55", tutar_kurus="3,00")).status_code, 302)
        diger = Cari.objects.create(unvan="Başka")
        self.assertEqual(self.client.post(reverse("belge_yeni", args=[diger.pk]), self.veri(evrak_no="55", tutar_kurus="4,00")).status_code, 302)

    def test_cift_giris_uyarisi_ve_yine_de(self):
        self.client.post(self.url, self.veri(evrak_no="1"))
        r = self.client.post(self.url, self.veri(evrak_no="2"))                       # aynı gün/tür/tutar
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "zaten var")
        self.assertContains(r, 'name="yine_de"')                                      # onay kutusu görünür
        self.assertEqual(Belge.objects.count(), 1)
        r = self.client.post(self.url, self.veri(evrak_no="2", yine_de="on"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Belge.objects.count(), 2)

    def test_farkli_gun_veya_tutar_uyari_vermez(self):
        self.client.post(self.url, self.veri(evrak_no="1"))
        self.assertEqual(self.client.post(self.url, self.veri(evrak_no="2", tarih="2026-03-06")).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.veri(evrak_no="3", tutar_kurus="1.250,51")).status_code, 302)

    def test_kaydet_ve_yenisini_ekle(self):
        r = self.client.post(self.url, self.veri(evrak_no="1", _yenisi="1", tur="ODEME"))
        self.assertRedirects(r, f"{self.url}?tur=ODEME")
        self.assertEqual(Belge.objects.count(), 1)

    def test_gunluge_yazilir_kullanici_adiyla(self):
        self.client.post(self.url, self.veri(evrak_no="1"))
        g = IslemGunlugu.objects.filter(model="Belge", islem="OLUSTURDU").first()
        self.assertIsNotNone(g)
        self.assertEqual(g.kullanici, "m")

    def test_olmayan_cari_404_get_ile_kayit_olmaz(self):
        self.assertEqual(self.client.get(reverse("belge_yeni", args=[99999])).status_code, 404)
        self.client.get(self.url, self.veri(evrak_no="g"))
        self.assertEqual(Belge.objects.count(), 0)

    def test_cari_formdan_degistirilemez(self):
        diger = Cari.objects.create(unvan="Başka")
        self.client.post(self.url, self.veri(cari=diger.pk, evrak_no="1"))
        self.assertEqual(Belge.objects.get().cari, self.cari)

    def test_html_kacar(self):
        r = self.client.post(self.url, self.veri(evrak_no="<script>q</script>", tutar_kurus="x"))
        self.assertNotContains(r, "<script>q</script>")


class YetkiTests(Temel):
    def test_yalniz_veri_girenler(self):
        for ad, rol, bek in (("g", "Görüntüleyici", 403), ("k", "Kasiyer", 403), ("r", None, 403)):
            self.client.force_login(rol_kullanici(ad, rol))
            self.assertEqual(self.client.get(self.url).status_code, bek, ad)
            self.assertEqual(self.client.post(self.url, self.veri()).status_code, bek, ad)
        self.assertEqual(Belge.objects.count(), 0)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_ekstre_dugmeleri_role_gore(self):
        ekstre = reverse("cari_ekstre", args=[self.cari.pk])
        r = self.client.get(ekstre)
        for p in ("Yeni alış", "Yeni ödeme", "Yeni iade", "belge/yeni"):
            self.assertContains(r, p)
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        r = self.client.get(ekstre)
        for p in ("Yeni alış", "Yeni ödeme", "belge/yeni", "satir-iptal"):
            self.assertNotContains(r, p)


class IptalTests(Temel):
    def setUp(self):
        super().setUp()
        self.b = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 3, 5), tutar_kurus=50000, evrak_no="9")
        self.iptal = reverse("belge_iptal", args=[self.b.pk])

    def test_iptal_bakiyeden_duser_ve_gunluge_yazilir(self):
        r = self.client.post(self.iptal, {"neden": "yanlış cari"})
        self.assertRedirects(r, reverse("cari_ekstre", args=[self.cari.pk]))
        self.b.refresh_from_db()
        self.assertEqual((self.b.iptal, self.b.iptal_nedeni), (True, "yanlış cari"))
        self.assertEqual(self.cari.bakiye_kurus(), 0)
        g = IslemGunlugu.objects.filter(model="Belge").order_by("-id").first()
        self.assertEqual(g.kullanici, "m")
        self.assertEqual(g.degisiklik["İptal"], ["Hayır", "Evet"])

    def test_neden_zorunlu(self):
        for neden in ("", "   "):
            self.client.post(self.iptal, {"neden": neden})
        self.b.refresh_from_db()
        self.assertFalse(self.b.iptal)

    def test_get_olmaz_ve_tekrar_iptal_sorun_cikarmaz(self):
        self.assertEqual(self.client.get(self.iptal).status_code, 405)
        self.client.post(self.iptal, {"neden": "a"})
        r = self.client.post(self.iptal, {"neden": "b"}, follow=True)
        self.assertContains(r, "zaten iptal edilmiş")
        self.b.refresh_from_db()
        self.assertEqual(self.b.iptal_nedeni, "a")

    def test_yetkisiz_iptal_edemez(self):
        for ad, rol in (("g", "Görüntüleyici"), ("k", "Kasiyer")):
            self.client.force_login(rol_kullanici(ad, rol))
            self.assertEqual(self.client.post(self.iptal, {"neden": "x"}).status_code, 403, ad)
        self.b.refresh_from_db()
        self.assertFalse(self.b.iptal)

    def test_ekstrede_iptal_formu_ve_iptal_satiri_gizlenir(self):
        ekstre = reverse("cari_ekstre", args=[self.cari.pk])
        self.assertContains(self.client.get(ekstre), "satir-iptal")
        self.client.post(self.iptal, {"neden": "x"})
        self.assertNotContains(self.client.get(ekstre), 'value="9"')
        self.assertEqual(self.client.post(reverse("belge_iptal", args=[99999]), {"neden": "x"}).status_code, 404)
