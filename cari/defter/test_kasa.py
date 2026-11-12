from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from . import kasa_servisi as ks
from .models import Belge, Cari, Hesap, KasaHareketi, KasaKategori
from .test_yardimci import rol_kullanici

GIRIS, CIKIS = KasaHareketi.Yon.GIRIS, KasaHareketi.Yon.CIKIS


class KasaTemel(TestCase):
    def setUp(self):
        self.kasa = Hesap.objects.get(ad="Ofis Kasa")

    def hareket(self, yon, tutar, tarih, **kw):
        return KasaHareketi.objects.create(hesap=self.kasa, yon=yon, tutar_kurus=tutar, tarih=tarih, **kw)


class EksiBakiyeTests(KasaTemel):
    def setUp(self):
        super().setUp()
        Hesap.objects.filter(pk=self.kasa.pk).update(eksiye_dusebilir=False)   # engel mekanizmasını sınamak için kapat
        self.kasa.refresh_from_db()

    def test_cikis_eksiye_dusuremez_giris_iptali_de_dusuremez(self):
        giris = self.hareket(GIRIS, 10000, date(2026, 3, 1))
        self.hareket(CIKIS, 6000, date(2026, 3, 2))
        giris.iptal, giris.iptal_nedeni = True, "yanlış"
        with self.assertRaises(ValidationError):
            giris.full_clean()                         # 10.000 giriş iptal -> bakiye -6.000
        fazla = KasaHareketi(hesap=self.kasa, yon=CIKIS, tutar_kurus=4001, tarih=date(2026, 3, 3))
        with self.assertRaises(ValidationError):
            fazla.full_clean()

    def test_iptali_zaten_iptal_olana_tekrar_sorun_cikarmaz(self):
        giris = self.hareket(GIRIS, 10000, date(2026, 3, 1))
        giris.iptal, giris.iptal_nedeni = True, "yanlış"
        giris.full_clean()
        giris.save()
        giris.refresh_from_db()
        giris.full_clean()                             # tekrar temiz: hata yok


class OfisKasaEksiVarsayilanTests(KasaTemel):
    def test_ofis_kasa_eksiden_baslayabilir(self):
        self.assertTrue(self.kasa.eksiye_dusebilir)
        h = KasaHareketi(hesap=self.kasa, yon=CIKIS, tutar_kurus=5000, tarih=date(2026, 3, 1))
        h.full_clean()
        h.save()
        self.assertEqual(self.kasa.bakiye_kurus(), -5000)
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.post(reverse("kasa"), {"tarih": "2026-03-02", "yon": "CIKIS", "tutar_kurus": "50,00", "kdv_modu": "BILINMIYOR"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.kasa.bakiye_kurus(), -10000)


class KasaHesapTests(KasaTemel):
    def test_aylik_ve_ay_sonu(self):
        self.hareket(GIRIS, 10000, date(2025, 12, 20))
        self.hareket(GIRIS, 5000, date(2026, 1, 5))
        self.hareket(CIKIS, 2000, date(2026, 2, 5))
        a = ks.kasa_aylik(self.kasa, 2026, bugun=date(2026, 2, 20))
        self.assertEqual((a["giris"][0], a["cikis"][1]), (5000, 2000))
        self.assertEqual(a["ay_sonu"][:3], [15000, 13000, None])

    def test_kategori_dagilimi_diger_toplanir_ve_kategorisiz(self):
        for ad, tutar in (("A", 500), ("B", 400), ("C", 300), ("D", 200)):
            k = KasaKategori.objects.create(ad=ad)
            self.hareket(GIRIS, 10000, date(2026, 1, 1)) if ad == "A" else None
            self.hareket(CIKIS, tutar, date(2026, 1, 2), kategori=k)
        self.hareket(CIKIS, 50, date(2026, 1, 3))
        d = ks.kategori_dagilimi(self.kasa, 2026, n=3)
        self.assertEqual(d, [("A", 500), ("B", 400), ("Diğer", 550)])
        self.assertIn(("Kategorisiz", 50), ks.kategori_dagilimi(self.kasa, 2026, n=8))

    def test_ozet_bugun_ve_ay(self):
        self.hareket(GIRIS, 10000, date(2026, 2, 28))
        self.hareket(GIRIS, 3000, date(2026, 3, 2))
        self.hareket(CIKIS, 1000, date(2026, 3, 10))
        o = ks.kasa_ozeti(self.kasa, bugun=date(2026, 3, 10))
        self.assertEqual((o["bakiye_kurus"], o["bugun_cikis"], o["bugun_giris"]), (12000, 1000, 0))
        self.assertEqual((o["ay_giris"], o["ay_cikis"]), (3000, 1000))

    def test_bakiyeli_liste_siralama(self):
        a = self.hareket(GIRIS, 1000, date(2026, 3, 1))
        b = self.hareket(CIKIS, 400, date(2026, 3, 2))
        self.assertEqual(ks.hareketler_bakiyeli(self.kasa), {a.pk: 1000, b.pk: 600})

    def test_en_buyuk_cikislar_sirali(self):
        self.hareket(GIRIS, 100000, date(2026, 1, 1))
        for t in (300, 900, 100):
            self.hareket(CIKIS, t, date(2026, 1, 2))
        self.assertEqual([h.tutar_kurus for h in ks.en_buyuk_cikislar(self.kasa, 2026, n=2)], [900, 300])


class OfisKasaBagimsizlikTests(KasaTemel):
    """Ofis Kasa ile cari defteri arasında HİÇBİR bağ olmamalı."""

    def test_kasa_hareketi_cari_bakiyesini_degistirmez(self):
        cari = Cari.objects.create(unvan="X")
        Belge.objects.create(cari=cari, tur="ALIS_FISI", tarih=date(2026, 1, 1), tutar_kurus=10000, evrak_no="1")
        self.hareket(GIRIS, 50000, date(2026, 1, 2))
        self.hareket(CIKIS, 7000, date(2026, 1, 3))
        self.assertEqual(cari.bakiye_kurus(), 10000)
        self.assertEqual(Belge.objects.count(), 1)

    def test_nakit_cari_odemesi_kasa_bakiyesini_degistirmez(self):
        cari = Cari.objects.create(unvan="X")
        self.hareket(GIRIS, 50000, date(2026, 1, 2))
        Belge.objects.create(cari=cari, tur="ODEME", tarih=date(2026, 1, 3), tutar_kurus=20000,
                             odeme_sekli="NAKIT")
        self.assertEqual(self.kasa.bakiye_kurus(), 50000)
        self.assertEqual(KasaHareketi.objects.count(), 1)
        self.assertEqual(cari.bakiye_kurus(), -20000)


class KasaEkranTests(KasaTemel):
    def setUp(self):
        super().setUp()
        self.user = rol_kullanici("p", "Muhasebe")
        self.bugun = date.today()

    def giris(self):
        self.client.force_login(self.user)

    def test_giris_gerekli(self):
        r = self.client.get(reverse("kasa"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])
        self.assertEqual(self.client.post(reverse("kasa_hareket_iptal", args=[1])).status_code, 302)

    def test_kasa_sayfasinda_cari_alani_yok(self):
        self.giris()
        Cari.objects.create(unvan="GORUNMEMELI CARI")
        r = self.client.get(reverse("kasa"))
        self.assertNotContains(r, "GORUNMEMELI CARI")
        self.assertNotContains(r, "name=\"cari\"")
        self.assertNotContains(r, "ilgili_odeme")
        self.assertNotContains(r, "kasa/kontrol")   # Ofis Kasa sayfasında kontrol bağlantısı yok

    def test_kasa_sayfasi_ve_hizli_giris(self):
        self.giris()
        r = self.client.get(reverse("kasa"))
        self.assertContains(r, "Ofis Kasa")
        self.assertContains(r, "chart.umd.js")
        r = self.client.post(reverse("kasa"), {"tarih": self.bugun.isoformat(), "yon": "GIRIS",
                                               "tutar_kurus": "1.234,50", "kdv_modu": "BILINMIYOR",
                                               "aciklama": "Nakit tahsilat"})
        self.assertEqual(r.status_code, 302)
        h = KasaHareketi.objects.get()
        self.assertEqual((h.tutar_kurus, h.yon, h.hesap_id), (123450, GIRIS, self.kasa.pk))
        self.assertContains(self.client.get(reverse("kasa")), "1.234,50")

    def test_belirsiz_tutar_ve_eksi_bakiye_reddedilir(self):
        self.giris()
        Hesap.objects.filter(pk=self.kasa.pk).update(eksiye_dusebilir=False)
        r = self.client.post(reverse("kasa"), {"tarih": self.bugun.isoformat(), "yon": "GIRIS",
                                               "tutar_kurus": "1234.50", "kdv_modu": "BILINMIYOR"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "1.234,50 biçiminde")
        r = self.client.post(reverse("kasa"), {"tarih": self.bugun.isoformat(), "yon": "CIKIS",
                                               "tutar_kurus": "50,00", "kdv_modu": "BILINMIYOR"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "eksiye düşür")
        self.assertEqual(KasaHareketi.objects.count(), 0)

    def test_kdv_ile_hizli_giris(self):
        self.giris()
        KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=10000000, tarih=self.bugun)
        self.client.post(reverse("kasa"), {"tarih": self.bugun.isoformat(), "yon": "CIKIS",
                                           "tutar_kurus": "1.000,00", "kdv_modu": "HARIC", "kdv_orani": "20"})
        h = KasaHareketi.objects.get(yon=CIKIS)
        self.assertEqual((h.matrah_kurus, h.kdv_kurus, h.tutar_kurus), (100000, 20000, 120000))

    def test_iptal_neden_ister(self):
        self.giris()
        h = KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=1000, tarih=self.bugun)
        url = reverse("kasa_hareket_iptal", args=[h.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        r = self.client.post(url, {"neden": ""}, follow=True)
        self.assertContains(r, "İptal için neden yazın")
        h.refresh_from_db()
        self.assertFalse(h.iptal)
        self.client.post(url, {"neden": "yanlış girildi"})
        h.refresh_from_db()
        self.assertTrue(h.iptal)
        self.assertEqual(h.iptal_nedeni, "yanlış girildi")

    def test_filtreler_ve_bozuk_parametreler_cokmez(self):
        self.giris()
        KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=1000, tarih=self.bugun, aciklama="GIRIS-A")
        KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=500, tarih=self.bugun,
                                    aciklama="IPTAL-B", iptal=True, iptal_nedeni="x")
        r = self.client.get(reverse("kasa"), {"yon": "GIRIS"})
        self.assertContains(r, "GIRIS-A")
        self.assertNotContains(r, "IPTAL-B")
        r = self.client.get(reverse("kasa"), {"iptal": "1"})
        self.assertContains(r, "IPTAL-B")
        self.assertEqual(self.client.get(reverse("kasa"), {"yon": "CIKIS"}).status_code, 200)
        for kotu in ({"bas": "abc"}, {"bit": "31.02.2026"}, {"yil": "x"}, {"sayfa": "999"}, {"hesap": "zzz"},
                     {"kategori": "q"}):
            self.assertEqual(self.client.get(reverse("kasa"), kotu).status_code, 200, kotu)

    def test_aktif_kasa_yoksa_bilgi(self):
        self.giris()
        Hesap.objects.update(aktif=False)
        self.assertContains(self.client.get(reverse("kasa")), "Aktif kasa hesabı yok")



class KasaAdminTests(KasaTemel):
    def setUp(self):
        super().setUp()
        self.client.force_login(get_user_model().objects.create_superuser("a", password="Guclu-Parola-9"))

    def test_toplu_iptal(self):
        a = self.hareket(GIRIS, 1000, date(2026, 3, 1))
        b = self.hareket(GIRIS, 2000, date(2026, 3, 10))
        self.client.post(reverse("admin:defter_kasahareketi_changelist"), {
            "action": "kasa_iptal_et", "_selected_action": [a.pk, b.pk]}, follow=True)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertTrue(a.iptal and b.iptal)


class CariKasaKaldirildiTests(TestCase):
    """Cari Kasa kaldırıldı (0015): tek kasa Ofis Kasa; cari/ilgili ödeme alanları ve kontrol ekranı yok."""

    def setUp(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))

    def test_tek_kasa_ofis_kasa(self):
        self.assertEqual(list(Hesap.objects.values_list("ad", flat=True)), ["Ofis Kasa"])

    def test_alanlar_ve_sayfalar_yok(self):
        alanlar = {f.name for f in KasaHareketi._meta.get_fields()}
        self.assertFalse({"cari", "ilgili_odeme"} & alanlar)
        self.assertFalse({"cari_bagli", "sadece_cikis", "on_yuzde_gizli"} & {f.name for f in Hesap._meta.get_fields()})
        self.assertEqual(self.client.get("/kasa/kontrol/").status_code, 404)
        r = self.client.get(reverse("kasa"))
        for yok in ("Cari Kasa", "(cari)", "Cari ödemesi kontrolü", 'name="cari"', "ilgili_odeme", "Kasa seçimi"):
            self.assertNotContains(r, yok)
        self.assertContains(r, "küçük harcamalar")

    def test_istek_baska_kasa_idsiyle_ofise_yazamaz(self):
        """Var olan ama aktif olmayan bir kasa id'sine yazma, sessizce Ofis Kasa'ya düşmez."""
        pasif = Hesap.objects.create(ad="Eski", aktif=False)
        n = KasaHareketi.objects.count()
        r = self.client.post(f"{reverse('kasa')}?hesap={pasif.pk}", {
            "tarih": date.today().isoformat(), "yon": "GIRIS", "tutar_kurus": "10,00", "kdv_modu": "BILINMIYOR"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(KasaHareketi.objects.count(), n)
        self.assertEqual(self.client.get(reverse("kasa"), {"hesap": pasif.pk}).context["hesap"].ad, "Ofis Kasa")


class GunSonuKaldirildiTests(KasaTemel):
    def test_sayfa_ve_baglantilar_yok(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.assertEqual(self.client.get("/kasa/gun-sonu/").status_code, 404)
        r = self.client.get(reverse("kasa"))
        for metin in ("Gün sonu", "Son kapanış", "kapanış bekliyor", "kapalı gün"):
            self.assertNotContains(r, metin)

    def test_eski_gun_sonu_kaydi_olsa_bile_kayit_engellenmez(self):
        from .models import GunSonu
        GunSonu.objects.create(hesap=self.kasa, tarih=date(2026, 3, 1), beklenen_kurus=0, sayilan_kurus=0, fark_kurus=0, kilitli=True)
        h = self.hareket(GIRIS, 1000, date(2026, 2, 1))                      # kilitli güne/öncesine girilebilir
        h.aciklama = "düzeltildi"
        h.save()
        self.assertEqual(KasaHareketi.objects.get().aciklama, "düzeltildi")
