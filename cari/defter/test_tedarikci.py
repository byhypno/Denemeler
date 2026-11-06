"""Tedarikçiler sayfası, ekleme/düzenleme formu, Türkçe duyarsız arama ve yönetim paneli aramalı seçim."""
from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import metin
from .models import Belge, Cari, IslemGunlugu
from .test_yardimci import rol_kullanici


class MetinTests(SimpleTestCase):
    def test_katla_turkce_ve_aksan(self):
        self.assertEqual(metin.katla("ERÖZ HIRDAVAT"), "eroz hirdavat")
        self.assertEqual(metin.katla("Eröz  Hırdavat "), "eroz hirdavat")
        self.assertEqual(metin.katla("İŞÇİ"), "isci")
        self.assertEqual(metin.katla(None), "")

    def test_eslesir_tum_sozcukler(self):
        self.assertTrue(metin.eslesir("eroz hird", "ERÖZ HIRDAVAT"))
        self.assertTrue(metin.eslesir("hırdavat eröz", "ERÖZ HIRDAVAT"))   # sıra önemsiz
        self.assertFalse(metin.eslesir("eroz boya", "ERÖZ HIRDAVAT"))
        self.assertTrue(metin.eslesir("", "x"))
        self.assertTrue(metin.eslesir("0555", "", "Ali", "0555 111"))      # birden çok alan


class TedarikciListeTests(TestCase):
    def setUp(self):
        self.a = Cari.objects.create(unvan="ERÖZ HIRDAVAT", kisa_kod="EROZ", vade_gun=30)
        self.b = Cari.objects.create(unvan="Çelik Sanayi", yetkili="Ayşe Kaya")
        self.p = Cari.objects.create(unvan="Eski Boya", aktif=False)
        Belge.objects.create(cari=self.a, tur=Belge.Tur.ALIS_FISI, tarih=date(2026, 3, 5), tutar_kurus=500000)
        Belge.objects.create(cari=self.b, tur=Belge.Tur.ALIS_FISI, tarih=date(2026, 5, 5), tutar_kurus=100000)
        Belge.objects.create(cari=self.b, tur=Belge.Tur.ODEME, tarih=date(2026, 5, 6), tutar_kurus=30000)
        self.client.force_login(rol_kullanici("y", is_superuser=True))
        self.url = reverse("tedarikciler")

    def adlar(self, r):
        return [x["cari"].unvan for x in r.context["satirlar"]]

    def test_varsayilan_borca_gore_pasif_gizli(self):
        r = self.client.get(self.url)
        self.assertEqual(self.adlar(r), ["ERÖZ HIRDAVAT", "Çelik Sanayi"])
        self.assertEqual(r.context["toplam_borc"], 500000 + 70000)

    def test_pasifleri_goster(self):
        self.assertIn("Eski Boya", self.adlar(self.client.get(self.url, {"pasif": "1"})))

    def test_arama_turkce_ve_aksansiz(self):
        for q in ("eroz", "EROZ", "eröz", "ERÖZ hird", "ayse kaya", "celik"):
            self.assertEqual(len(self.client.get(self.url, {"q": q}).context["satirlar"]), 1, q)
        self.assertEqual(self.adlar(self.client.get(self.url, {"q": "yokboyle"})), [])

    def test_siralama_ada_ve_son_harekete_gore(self):
        self.assertEqual(self.adlar(self.client.get(self.url, {"sira": "unvan"})), ["Çelik Sanayi", "ERÖZ HIRDAVAT"])
        self.assertEqual(self.adlar(self.client.get(self.url, {"sira": "son"})), ["Çelik Sanayi", "ERÖZ HIRDAVAT"])
        self.assertEqual(self.adlar(self.client.get(self.url, {"sira": "saçma"})), ["ERÖZ HIRDAVAT", "Çelik Sanayi"])

    def test_iptal_belge_bakiyeye_ve_son_harekete_girmez(self):
        Belge.objects.create(cari=self.b, tur=Belge.Tur.ALIS_FISI, tarih=date(2026, 9, 1), tutar_kurus=999999, iptal=True, iptal_nedeni="test")
        satir = [x for x in self.client.get(self.url).context["satirlar"] if x["cari"] == self.b][0]
        self.assertEqual(satir["bakiye"], 70000)
        self.assertEqual(satir["son"], date(2026, 5, 6))

    def test_bos_durum(self):
        r = self.client.get(self.url, {"q": "zzz"})
        self.assertContains(r, "Eşleşen tedarikçi yok")

    def test_html_kacar(self):
        Cari.objects.create(unvan="<script>x</script> Ltd")
        self.assertNotContains(self.client.get(self.url), "<script>x</script>")

    def test_kart_ekstreye_baglanir_ve_menu_isaretli(self):
        r = self.client.get(self.url)
        self.assertContains(r, reverse("cari_ekstre", args=[self.a.pk]))
        self.assertContains(r, 'aria-current="page"')


class TedarikciYetkiTests(TestCase):
    def setUp(self):
        self.c = Cari.objects.create(unvan="Deneme")

    def test_goruntuleyici_listeyi_gorur_ekleyemez(self):
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        r = self.client.get(reverse("tedarikciler"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, reverse("tedarikci_yeni"))
        self.assertNotContains(r, "Düzenle")
        self.assertEqual(self.client.get(reverse("tedarikci_yeni")).status_code, 403)
        self.assertEqual(self.client.post(reverse("tedarikci_yeni"), {"unvan": "X"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("tedarikci_duzenle", args=[self.c.pk])).status_code, 403)
        self.assertFalse(Cari.objects.filter(unvan="X").exists())

    def test_kasiyer_hic_goremez(self):
        self.client.force_login(rol_kullanici("k", "Kasiyer"))
        self.assertEqual(self.client.get(reverse("tedarikciler")).status_code, 403)
        self.assertEqual(self.client.get(reverse("tedarikci_yeni")).status_code, 403)

    def test_giris_yapmamis_girise_yonlenir(self):
        r = self.client.get(reverse("tedarikciler"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])

    def test_muhasebe_ekleyebilir(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.get(reverse("tedarikciler"))
        self.assertContains(r, reverse("tedarikci_yeni"))
        self.assertEqual(self.client.get(reverse("tedarikci_yeni")).status_code, 200)


class TedarikciFormTests(TestCase):
    def setUp(self):
        self.u = rol_kullanici("m", "Muhasebe")
        self.client.force_login(self.u)
        self.yeni = reverse("tedarikci_yeni")

    def test_ekle_ekstreye_yonlendirir_ve_gunluge_yazar(self):
        r = self.client.post(self.yeni, {"unvan": "  Yeni   Tedarik  Ltd ", "vade_gun": "45", "yetkili": "Ali"})
        c = Cari.objects.get(unvan="Yeni Tedarik Ltd")              # boşluklar toparlanır
        self.assertRedirects(r, reverse("cari_ekstre", args=[c.pk]))
        self.assertEqual((c.vade_gun, c.yetkili, c.aktif), (45, "Ali", True))
        g = IslemGunlugu.objects.filter(model="Cari", nesne_id=c.pk).first()
        self.assertIsNotNone(g)
        self.assertEqual(g.kullanici, "m")

    def test_unvan_zorunlu(self):
        r = self.client.post(self.yeni, {"unvan": "  "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Cari.objects.count(), 0)
        self.assertContains(r, "Bu alan zorunlu")

    def test_ayni_unvan_turkce_farkli_yazimla_reddedilir(self):
        Cari.objects.create(unvan="ERÖZ HIRDAVAT")
        for yazim in ("Eröz Hırdavat", "eroz hirdavat", "EROZ  HIRDAVAT"):
            r = self.client.post(self.yeni, {"unvan": yazim})
            self.assertEqual(r.status_code, 200, yazim)
            self.assertContains(r, "zaten kayıtlı")
        self.assertEqual(Cari.objects.count(), 1)

    def test_vade_sinirlari(self):
        for v in ("-1", "366", "abc"):
            self.assertEqual(self.client.post(self.yeni, {"unvan": "A" + v, "vade_gun": v}).status_code, 200, v)
        self.assertEqual(Cari.objects.count(), 0)
        self.assertEqual(self.client.post(self.yeni, {"unvan": "Sinir", "vade_gun": "365"}).status_code, 302)

    def test_yeni_formda_aktif_alani_yok_duzenlemede_var(self):
        self.assertNotContains(self.client.get(self.yeni), 'name="aktif"')
        c = Cari.objects.create(unvan="Mevcut")
        self.assertContains(self.client.get(reverse("tedarikci_duzenle", args=[c.pk])), 'name="aktif"')

    def test_duzenle_ve_pasif_yap(self):
        c = Cari.objects.create(unvan="Mevcut")
        url = reverse("tedarikci_duzenle", args=[c.pk])
        r = self.client.post(url, {"unvan": "Mevcut Yeni", "telefon": "123"})        # aktif işaretsiz => pasif
        self.assertRedirects(r, reverse("tedarikciler"))
        c.refresh_from_db()
        self.assertEqual((c.unvan, c.telefon, c.aktif), ("Mevcut Yeni", "123", False))

    def test_kendi_unvanini_koruyarak_duzenleyebilir(self):
        c = Cari.objects.create(unvan="Mevcut")
        r = self.client.post(reverse("tedarikci_duzenle", args=[c.pk]), {"unvan": "MEVCUT", "aktif": "on"})
        self.assertEqual(r.status_code, 302)

    def test_olmayan_kayit_404(self):
        self.assertEqual(self.client.get(reverse("tedarikci_duzenle", args=[9999])).status_code, 404)

    def test_get_ile_kayit_olusmaz(self):
        self.client.get(self.yeni, {"unvan": "GetIle"})
        self.assertFalse(Cari.objects.filter(unvan="GetIle").exists())


class YonetimAramaliSecimTests(TestCase):
    def setUp(self):
        Cari.objects.create(unvan="ERÖZ HIRDAVAT")
        Cari.objects.create(unvan="Çelik Sanayi")
        Cari.objects.create(unvan="Eski Eroz Boya", aktif=False)
        self.client.force_login(rol_kullanici("y", is_superuser=True, is_staff=True))

    def ara(self, term):
        r = self.client.get(reverse("admin:autocomplete"), {"term": term, "app_label": "defter", "model_name": "belge", "field_name": "cari"})
        self.assertEqual(r.status_code, 200)
        return [x["text"] for x in r.json()["results"]]

    def test_belge_formunda_cari_aramali(self):
        h = self.client.get(reverse("admin:defter_belge_add")).content.decode()
        self.assertIn("admin-autocomplete", h)

    def test_turkce_duyarsiz_ve_pasif_cikmaz(self):
        self.assertEqual(self.ara("eroz"), ["ERÖZ HIRDAVAT"])        # "Eski Eroz Boya" pasif: çıkmaz
        self.assertEqual(self.ara("CELIK"), ["Çelik Sanayi"])
        self.assertEqual(self.ara("yok"), [])

    def test_liste_aramasi_pasifleri_de_bulur(self):
        r = self.client.get(reverse("admin:defter_cari_changelist"), {"q": "eroz"})
        self.assertContains(r, "Eski Eroz Boya")
        self.assertContains(r, "ERÖZ HIRDAVAT")

    def test_diger_formlar_da_aramali(self):
        for ad in ("admin:defter_kasahareketi_add", "admin:defter_ekstremutabakat_add"):
            self.assertIn("admin-autocomplete", self.client.get(reverse(ad)).content.decode(), ad)
