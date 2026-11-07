"""Veri girişi merkezi ve kasa 'Harcayan' alanı."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from . import kasa_servisi as ks
from .models import Belge, Cari, Hesap, IslemGunlugu, KasaHareketi
from .test_yardimci import rol_kullanici


class VeriGirisiTests(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="Demir A.Ş.")

    def test_anonim_girise_yonlenir(self):
        r = self.client.get(reverse("veri_girisi"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])

    def test_menude_rollere_gore_gorunur(self):
        for rol, gorunur in (("Muhasebe", True), ("Kasiyer", False), ("Görüntüleyici", False)):
            self.client.force_login(rol_kullanici("u" + rol[:3], rol))
            r = self.client.get(reverse("kasa" if rol == "Kasiyer" else "dashboard"))
            self.assertEqual(reverse("veri_girisi") in r.content.decode(), gorunur, rol)
            self.client.logout()

    def test_kasiyer_ve_goruntuleyici_sayfaya_giremez(self):
        for rol in ("Kasiyer", "Görüntüleyici"):
            self.client.force_login(rol_kullanici("x" + rol[:3], rol))
            self.assertNotEqual(self.client.get(reverse("veri_girisi")).status_code, 200, rol)
            self.client.logout()

    def test_sayfa_kartlari_ve_tedarikci_secimi(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.get(reverse("veri_girisi"))
        self.assertContains(r, "Demir A.Ş.")
        for metin in ("Kasa hareketi", "Aylık genel gider", "Malzemeler"):
            self.assertContains(r, metin)
        self.assertContains(r, "Gelişmiş işler")

    def test_yonetim_karti_yalniz_staff(self):
        self.client.force_login(rol_kullanici("s", None, is_staff=True, is_superuser=True))
        self.assertContains(self.client.get(reverse("veri_girisi")), "Gelişmiş işler")
        u = rol_kullanici("g", "Görüntüleyici")
        self.assertFalse(u.is_staff)

    def test_secilen_tedarikci_belge_formuna_gider(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.get(reverse("veri_girisi"), {"cari": self.cari.pk, "tur": Belge.Tur.ODEME})
        self.assertRedirects(r, f"{reverse('belge_yeni', args=[self.cari.pk])}?tur={Belge.Tur.ODEME}",
                             fetch_redirect_response=False)

    def test_gecersiz_tur_alis_fisine_duser(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.get(reverse("veri_girisi"), {"cari": self.cari.pk, "tur": "SACMA"})
        self.assertIn(f"tur={Belge.Tur.ALIS_FISI}", r["Location"])

    def test_gecersiz_tedarikci_uyari_verir(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.get(reverse("veri_girisi"), {"cari": "99999", "tur": Belge.Tur.ODEME})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Önce tedarikçiyi seçin")
        r = self.client.get(reverse("veri_girisi"), {"cari": "abc"})
        self.assertEqual(r.status_code, 200)


class HarcayanTests(TestCase):
    def setUp(self):
        self.kasa = Hesap.objects.get(ad="Ofis Kasa")

    def h(self, harcayan, yon=KasaHareketi.Yon.CIKIS, tutar=100):
        return KasaHareketi.objects.create(hesap=self.kasa, yon=yon, tutar_kurus=tutar,
                                           tarih=date.today(), harcayan=harcayan)

    def test_bosluklar_temizlenir_ve_kaydedilir(self):
        self.h("", yon=KasaHareketi.Yon.GIRIS, tutar=100000)
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.post(reverse("kasa"), {"tarih": date.today().isoformat(), "yon": "CIKIS",
                                               "tutar_kurus": "5,00", "kdv_modu": "BILINMIYOR",
                                               "harcayan": "  Mehmet   Öz  "})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        self.assertEqual(KasaHareketi.objects.filter(yon="CIKIS").get().harcayan, "Mehmet Öz")

    def test_oneriler_tekil_ve_turkce_sirali(self):
        for ad in ("Şule", "Ahmet", "ahmet", "Çiğdem", "", "Zeynep"):
            self.h(ad)
        self.assertEqual(ks.harcayanlar(self.kasa), ["Ahmet", "Çiğdem", "Şule", "Zeynep"])

    def test_kasa_sayfasinda_sutun_ve_oneri_listesi(self):
        self.h("Mehmet")
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.get(reverse("kasa"))
        self.assertContains(r, "Harcayan")
        self.assertContains(r, 'id="harcayan-listesi"')
        self.assertContains(r, "Mehmet")

    def test_gunluge_yazilir(self):
        self.h("Mehmet")
        kayit = IslemGunlugu.objects.filter(model="KasaHareketi").latest("id")
        self.assertIn("Mehmet", str(kayit.degisiklik))


class KasaDuzeltTests(TestCase):
    def setUp(self):
        self.kasa = Hesap.objects.get(ad="Ofis Kasa")
        self.h = KasaHareketi.objects.create(hesap=self.kasa, yon=KasaHareketi.Yon.CIKIS, tutar_kurus=5000,
                                             tarih=date.today(), aciklama="eski", harcayan="Ali")
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.url = reverse("kasa_hareket_duzelt", args=[self.h.pk])

    def test_ust_veri_duzelir_tutar_tarih_yon_degismez(self):
        r = self.client.post(self.url, {"aciklama": " yeni\x0b açıklama ", "harcayan": "Veli", "makbuz_no": "7",
                                        "tutar_kurus": "999,00", "tarih": "2001-01-01", "yon": "GIRIS"})
        self.assertEqual(r.status_code, 302)
        self.h.refresh_from_db()
        self.assertEqual((self.h.aciklama, self.h.harcayan, self.h.makbuz_no), ("yeni açıklama", "Veli", "7"))
        self.assertEqual((self.h.tutar_kurus, self.h.tarih, self.h.yon), (5000, date.today(), KasaHareketi.Yon.CIKIS))

    def test_gunluge_yazilir(self):
        self.client.post(self.url, {"aciklama": "yeni", "harcayan": "Veli", "makbuz_no": ""})
        kayit = IslemGunlugu.objects.filter(model="KasaHareketi", islem="DEGISTI").latest("id")
        self.assertIn("Veli", str(kayit.degisiklik))

    def test_iptal_edilmis_duzeltilemez(self):
        KasaHareketi.objects.filter(pk=self.h.pk).update(iptal=True, iptal_nedeni="x")
        r = self.client.post(self.url, {"aciklama": "yeni", "harcayan": "Z", "makbuz_no": ""})
        self.assertEqual(r.status_code, 302)
        self.h.refresh_from_db()
        self.assertEqual(self.h.harcayan, "Ali")

    def test_kapali_gun_duzeltilemez(self):
        from unittest import mock
        with mock.patch.object(Hesap, "kilit_siniri", return_value=date.today()):
            self.client.post(self.url, {"aciklama": "yeni", "harcayan": "Z", "makbuz_no": ""})
        self.h.refresh_from_db()
        self.assertEqual(self.h.harcayan, "Ali")

    def test_yetki(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(rol_kullanici("k", "Kasiyer"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_form_sayfasi_ve_baglanti(self):
        self.assertContains(self.client.get(self.url), "Kasa kaydını düzelt")
        self.assertContains(self.client.get(reverse("kasa")), self.url)
