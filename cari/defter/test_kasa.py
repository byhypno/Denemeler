from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from . import kasa_servisi as ks
from .models import Belge, Cari, GunSonu, Hesap, KasaHareketi, KasaKategori

GIRIS, CIKIS = KasaHareketi.Yon.GIRIS, KasaHareketi.Yon.CIKIS


class KasaTemel(TestCase):
    def setUp(self):
        self.kasa = Hesap.objects.get(ad="Ofis Kasa")

    def hareket(self, yon, tutar, tarih, **kw):
        return KasaHareketi.objects.create(hesap=self.kasa, yon=yon, tutar_kurus=tutar, tarih=tarih, **kw)


class GunSonuKilitTests(KasaTemel):
    def test_beklenen_acilis_bakiyesini_ve_tarihe_kadar_olani_icerir(self):
        self.kasa.acilis_bakiye_kurus = 5000
        self.kasa.save()
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        self.hareket(CIKIS, 3000, date(2026, 3, 2))
        self.hareket(GIRIS, 99999, date(2026, 3, 5))      # sonraki gün: dahil değil
        self.assertEqual(ks.gun_sonu_beklenen(self.kasa, date(2026, 3, 2)), 12000)

    def test_iptal_beklenene_dahil_degil(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        self.hareket(GIRIS, 5000, date(2026, 3, 1), iptal=True, iptal_nedeni="hatalı")
        self.assertEqual(ks.gun_sonu_beklenen(self.kasa, date(2026, 3, 1)), 10000)

    def test_kapanis_tutarsa_fark_sifir_ve_kilitler(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        g = ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 10000, bugun=date(2026, 3, 2))
        self.assertEqual((g.beklenen_kurus, g.sayilan_kurus, g.fark_kurus, g.kilitli), (10000, 10000, 0, True))
        self.assertEqual(self.kasa.kilit_siniri(), date(2026, 3, 1))

    def test_kapali_gune_kayit_girilemez(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 10000, bugun=date(2026, 3, 2))
        yeni = KasaHareketi(hesap=self.kasa, yon=GIRIS, tutar_kurus=100, tarih=date(2026, 3, 1))
        with self.assertRaises(ValidationError):
            yeni.full_clean()
        with self.assertRaises(ValidationError):
            yeni.save()                       # clean'i atlayan doğrudan kayıt da engellenir
        with self.assertRaises(ValidationError):
            self.hareket(GIRIS, 100, date(2026, 2, 15))   # daha eski gün de kapalı
        self.assertEqual(KasaHareketi.objects.count(), 1)

    def test_kapali_gunun_kaydi_degistirilemez_veya_iptal_edilemez(self):
        h = self.hareket(GIRIS, 10000, date(2026, 3, 1))
        ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 10000, bugun=date(2026, 3, 2))
        h.tutar_kurus = 1
        with self.assertRaises(ValidationError):
            h.save()
        h.refresh_from_db()
        h.iptal, h.iptal_nedeni = True, "x"
        with self.assertRaises(ValidationError):
            h.full_clean()
        h.refresh_from_db()
        self.assertEqual((h.tutar_kurus, h.iptal), (10000, False))

    def test_sonraki_gun_serbest(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 10000, bugun=date(2026, 3, 2))
        self.hareket(CIKIS, 4000, date(2026, 3, 2))
        self.assertEqual(self.kasa.bakiye_kurus(), 6000)

    def test_noksan_farki_cikis_hareketi_olarak_isler(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        g = ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 9000, farki_isle=True, bugun=date(2026, 3, 2))
        self.assertEqual((g.fark_kurus, g.fark_islendi), (-1000, True))
        fark = KasaHareketi.objects.get(kategori__ad=ks.KASA_FARKI)
        self.assertEqual((fark.yon, fark.tutar_kurus, fark.tarih), (CIKIS, 1000, date(2026, 3, 1)))
        self.assertEqual(self.kasa.bakiye_kurus(), 9000)        # artık sayılanla aynı

    def test_fazla_farki_giris_hareketi_olarak_isler(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 10250, farki_isle=True, bugun=date(2026, 3, 2))
        self.assertEqual(KasaHareketi.objects.get(kategori__ad=ks.KASA_FARKI).yon, GIRIS)
        self.assertEqual(self.kasa.bakiye_kurus(), 10250)

    def test_fark_islenmezse_hareket_olusmaz(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        g = ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 9000, bugun=date(2026, 3, 2))
        self.assertEqual((g.fark_kurus, g.fark_islendi), (-1000, False))
        self.assertEqual(KasaHareketi.objects.count(), 1)

    def test_gecersiz_kapanislar(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        with self.assertRaises(ValidationError):
            ks.gun_sonu_kapat(self.kasa, date(2026, 3, 9), 0, bugun=date(2026, 3, 2))       # gelecek
        with self.assertRaises(ValidationError):
            ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), -5, bugun=date(2026, 3, 2))      # eksi sayım
        ks.gun_sonu_kapat(self.kasa, date(2026, 3, 5), 10000, bugun=date(2026, 3, 6))
        for gun in (date(2026, 3, 5), date(2026, 3, 4)):                                    # tekrar / geri
            with self.assertRaises(ValidationError):
                ks.gun_sonu_kapat(self.kasa, gun, 10000, bugun=date(2026, 3, 6))
        self.assertEqual(GunSonu.objects.count(), 1)

    def test_gun_sonu_tarihi_tekil(self):
        GunSonu.objects.create(hesap=self.kasa, tarih=date(2026, 3, 1), beklenen_kurus=0,
                               sayilan_kurus=0, fark_kurus=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            GunSonu.objects.create(hesap=self.kasa, tarih=date(2026, 3, 1), beklenen_kurus=0,
                                   sayilan_kurus=0, fark_kurus=0)

    def test_kilit_acilinca_kayit_girilebilir(self):
        self.hareket(GIRIS, 10000, date(2026, 3, 1))
        g = ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 10000, bugun=date(2026, 3, 2))
        g.kilitli = False
        g.save()
        self.assertIsNone(self.kasa.kilit_siniri())
        self.hareket(GIRIS, 100, date(2026, 3, 1))

    def test_acik_gunler(self):
        self.hareket(GIRIS, 100, date(2026, 3, 1))
        self.hareket(GIRIS, 100, date(2026, 3, 3))
        self.hareket(GIRIS, 100, date(2026, 3, 9))   # bugün: sayılmaz
        self.assertEqual(ks.acik_gunler(self.kasa, date(2026, 3, 9)), [date(2026, 3, 1), date(2026, 3, 3)])
        ks.gun_sonu_kapat(self.kasa, date(2026, 3, 1), 100, bugun=date(2026, 3, 9))
        self.assertEqual(ks.acik_gunler(self.kasa, date(2026, 3, 9)), [date(2026, 3, 3)])


class EksiBakiyeTests(KasaTemel):
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


class KasaKontrolTests(KasaTemel):
    def setUp(self):
        super().setUp()
        self.cari = Cari.objects.create(unvan="K")
        self.hareket(GIRIS, 1000000, date(2026, 1, 1))

    def odeme(self, tutar, tarih, sekil="NAKIT", cari=None):
        return Belge.objects.create(cari=cari or self.cari, tur="ODEME", tutar_kurus=tutar, tarih=tarih,
                                    odeme_sekli=sekil)

    def test_nakit_odeme_kasasiz_listelenir_havale_listelenmez(self):
        self.odeme(5000, date(2026, 1, 10), "NAKIT")
        self.odeme(7000, date(2026, 1, 10), "HAVALE")
        k = ks.kasa_kontrol()
        self.assertEqual([x["odeme"].tutar_kurus for x in k["nakit_kasasiz"]], [5000])
        self.assertIsNone(k["nakit_kasasiz"][0]["oneri"])

    def test_tek_aday_oneri_olur(self):
        o = self.odeme(5000, date(2026, 1, 10))
        c = self.hareket(CIKIS, 5000, date(2026, 1, 11), cari=self.cari)
        k = ks.kasa_kontrol()
        self.assertEqual(k["nakit_kasasiz"][0]["oneri"], c)
        self.assertEqual(k["kasa_odemesiz"][0]["oneri"], o)
        self.assertEqual(k["adet"], 2)

    def test_uzak_tarih_veya_farkli_tutar_oneri_degildir(self):
        self.odeme(5000, date(2026, 1, 10))
        self.hareket(CIKIS, 5000, date(2026, 1, 20), cari=self.cari)      # 10 gün fark
        self.hareket(CIKIS, 4999, date(2026, 1, 10), cari=self.cari)      # tutar farklı
        k = ks.kasa_kontrol()
        self.assertIsNone(k["nakit_kasasiz"][0]["oneri"])

    def test_birden_fazla_aday_oneri_vermez(self):
        self.odeme(5000, date(2026, 1, 10))
        self.hareket(CIKIS, 5000, date(2026, 1, 10), cari=self.cari)
        self.hareket(CIKIS, 5000, date(2026, 1, 11), cari=self.cari)
        k = ks.kasa_kontrol()
        self.assertIsNone(k["nakit_kasasiz"][0]["oneri"])
        self.assertEqual(k["nakit_kasasiz"][0]["aday_sayisi"], 2)

    def test_baglanan_listeden_cikar(self):
        o = self.odeme(5000, date(2026, 1, 10))
        c = self.hareket(CIKIS, 5000, date(2026, 1, 10), cari=self.cari)
        ks.eslestir(c.pk, o.pk)
        c.refresh_from_db()
        self.assertEqual(c.ilgili_odeme_id, o.pk)
        self.assertEqual(ks.kasa_kontrol()["adet"], 0)
        self.assertEqual(self.kasa.bakiye_kurus(), 1000000 - 5000)        # tutarlar değişmedi
        self.assertEqual(Belge.objects.count(), 1)

    def test_eslestirme_dogrulamalari(self):
        baska = Cari.objects.create(unvan="Baska")
        o = self.odeme(5000, date(2026, 1, 10))
        c_baska = self.hareket(CIKIS, 5000, date(2026, 1, 10), cari=baska)
        with self.assertRaises(ValidationError):
            ks.eslestir(c_baska.pk, o.pk)                                  # farklı cari
        c1 = self.hareket(CIKIS, 5000, date(2026, 1, 10), cari=self.cari)
        c2 = self.hareket(CIKIS, 5000, date(2026, 1, 11), cari=self.cari)
        ks.eslestir(c1.pk, o.pk)
        with self.assertRaises(ValidationError):
            ks.eslestir(c2.pk, o.pk)                                       # aynı ödeme iki kez bağlanamaz

    def test_kapali_gundeki_kayit_da_eslestirilebilir(self):
        o = self.odeme(5000, date(2026, 1, 10))
        c = self.hareket(CIKIS, 5000, date(2026, 1, 10), cari=self.cari)
        ks.gun_sonu_kapat(self.kasa, date(2026, 1, 15), self.kasa.bakiye_kurus(), bugun=date(2026, 1, 16))
        ks.eslestir(c.pk, o.pk)
        c.refresh_from_db()
        self.assertEqual(c.ilgili_odeme_id, o.pk)

    def test_iptaller_kontrole_girmez(self):
        self.odeme(5000, date(2026, 1, 10))
        Belge.objects.filter(tur="ODEME").update(iptal=True, iptal_nedeni="x")
        self.hareket(CIKIS, 100, date(2026, 1, 10), cari=self.cari, iptal=True, iptal_nedeni="x")
        self.assertEqual(ks.kasa_kontrol()["adet"], 0)


class KasaEkranTests(KasaTemel):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("p", password="x", is_staff=True)
        self.bugun = date.today()
        self.cari = Cari.objects.create(unvan="Ekran Cari")

    def giris(self):
        self.client.force_login(self.user)

    def test_giris_gerekli(self):
        for ad in ("kasa", "kasa_gun_sonu", "kasa_kontrol"):
            r = self.client.get(reverse(ad))
            self.assertEqual(r.status_code, 302, ad)
            self.assertIn("/admin/login/", r["Location"])
        self.assertEqual(self.client.post(reverse("kasa_hareket_iptal", args=[1])).status_code, 302)

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

    def test_kapali_gune_ekrandan_kayit_girilemez(self):
        self.giris()
        d = self.bugun - timedelta(days=3)
        KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=1000, tarih=d)
        ks.gun_sonu_kapat(self.kasa, d, 1000)
        r = self.client.post(reverse("kasa"), {"tarih": d.isoformat(), "yon": "GIRIS", "tutar_kurus": "1,00",
                                               "kdv_modu": "BILINMIYOR"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "kapatıldı")
        self.assertEqual(KasaHareketi.objects.count(), 1)

    def test_iptal_neden_ister_ve_kapali_gunu_reddeder(self):
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

    def test_kapali_gunun_iptali_ekranda_reddedilir(self):
        self.giris()
        d = self.bugun - timedelta(days=2)
        h = KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=1000, tarih=d)
        ks.gun_sonu_kapat(self.kasa, d, 1000)
        r = self.client.post(reverse("kasa_hareket_iptal", args=[h.pk]), {"neden": "x"}, follow=True)
        self.assertContains(r, "kapatılmış bir güne ait")
        h.refresh_from_db()
        self.assertFalse(h.iptal)

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
        self.assertContains(self.client.get(reverse("kasa_gun_sonu")), "Aktif kasa hesabı yok")

    def test_gun_sonu_ekrani(self):
        self.giris()
        d = self.bugun - timedelta(days=1)
        KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=250000, tarih=d)
        r = self.client.get(reverse("kasa_gun_sonu"), {"tarih": d.isoformat()})
        self.assertContains(r, "2.500,00 ₺")
        r = self.client.post(reverse("kasa_gun_sonu"), {"tarih": d.isoformat(), "sayilan": "2.400,00",
                                                        "aciklama": "sayım", "farki_isle": "on"})
        self.assertEqual(r.status_code, 302)
        g = GunSonu.objects.get()
        self.assertEqual((g.fark_kurus, g.fark_islendi), (-10000, True))
        r = self.client.get(reverse("kasa_gun_sonu"))
        self.assertContains(r, "Kasa noksanı")
        r = self.client.post(reverse("kasa_gun_sonu"), {"tarih": d.isoformat(), "sayilan": "2.400,00"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "zaten kapatılmış")
        r = self.client.post(reverse("kasa_gun_sonu"), {"tarih": d.isoformat(), "sayilan": "abc"})
        self.assertContains(r, "1.234,50 biçiminde")

    def test_gelecek_gun_ekrandan_kapatilamaz(self):
        self.giris()
        r = self.client.post(reverse("kasa_gun_sonu"), {"tarih": (self.bugun + timedelta(days=2)).isoformat(),
                                                        "sayilan": "0,00"})
        self.assertContains(r, "Gelecek bir gün")
        self.assertEqual(GunSonu.objects.count(), 0)

    def test_kontrol_ekrani_ve_eslestirme(self):
        self.giris()
        KasaHareketi.objects.create(hesap=self.kasa, yon=GIRIS, tutar_kurus=1000000, tarih=self.bugun)
        o = Belge.objects.create(cari=self.cari, tur="ODEME", tutar_kurus=5000, tarih=self.bugun, odeme_sekli="NAKIT")
        c = KasaHareketi.objects.create(hesap=self.kasa, yon=CIKIS, tutar_kurus=5000, tarih=self.bugun, cari=self.cari)
        r = self.client.get(reverse("kasa_kontrol"))
        self.assertContains(r, "Eşleştir")
        r = self.client.post(reverse("kasa_kontrol"), {"odeme": o.pk, "hareket": c.pk}, follow=True)
        self.assertContains(r, "Tutarsızlık yok")
        c.refresh_from_db()
        self.assertEqual(c.ilgili_odeme_id, o.pk)
        r = self.client.post(reverse("kasa_kontrol"), {"odeme": "x", "hareket": "y"}, follow=True)
        self.assertContains(r, "Kayıt bulunamadı")


class KasaAdminTests(KasaTemel):
    def setUp(self):
        super().setUp()
        self.client.force_login(get_user_model().objects.create_superuser("a", password="Guclu-Parola-9"))

    def test_gun_sonu_yonetimden_eklenemez_silinemez(self):
        self.assertEqual(self.client.get(reverse("admin:defter_gunsonu_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:defter_gunsonu_changelist")).status_code, 200)

    def test_toplu_iptal_kapali_gunu_atlar(self):
        eski = self.hareket(GIRIS, 1000, date(2026, 3, 1))
        yeni = self.hareket(GIRIS, 2000, date(2026, 3, 10))
        ks.gun_sonu_kapat(self.kasa, date(2026, 3, 5), 1000, bugun=date(2026, 3, 6))
        r = self.client.post(reverse("admin:defter_kasahareketi_changelist"), {
            "action": "kasa_iptal_et", "_selected_action": [eski.pk, yeni.pk]}, follow=True)
        self.assertContains(r, "İptal edilemedi")
        eski.refresh_from_db(); yeni.refresh_from_db()
        self.assertFalse(eski.iptal)
        self.assertTrue(yeni.iptal)
