"""Aylık net genel giderler: servis, ekran, yetki, günlük, Excel."""
from datetime import date
from io import BytesIO

import openpyxl
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from . import gider_servisi as gs
from . import trend
from .models import GenelGider, GiderKategori, IslemGunlugu
from .test_yardimci import rol_kullanici


class Temel(TestCase):
    def setUp(self):
        self.kira = GiderKategori.objects.get(ad="Kira")
        self.elektrik = GiderKategori.objects.get(ad="Elektrik")
        self.personel = GiderKategori.objects.get(ad="Personel")

    def g(self, kat, yil, ay, tutar, aciklama=""):
        return GenelGider.objects.create(kategori=kat, yil=yil, ay=ay, tutar_kurus=tutar, aciklama=aciklama)


class KarsilastirTests(TestCase):
    def test_yon_ve_yuzde(self):
        self.assertEqual(trend.karsilastir(150, 100), {"yon": "yukari", "yuzde": 50})
        self.assertEqual(trend.karsilastir(50, 100), {"yon": "asagi", "yuzde": 50})
        self.assertEqual(trend.karsilastir(7, 7), {"yon": "yatay", "yuzde": 0})
        self.assertEqual(trend.karsilastir(5, 0), {"yon": "yukari", "yuzde": None})


class KategoriTests(Temel):
    def test_varsayilan_kalemler_hazir(self):
        self.assertEqual(list(GiderKategori.objects.values_list("ad", flat=True)),
                         ["Kira", "Elektrik", "Su", "Mali müşavir", "Avukat", "Personel", "Diğer"])

    def test_tablo_kisitlari(self):
        self.g(self.kira, 2026, 1, 100)
        from django.db import IntegrityError, transaction
        for kw in ({"ay": 1}, {"ay": 13, "kategori": self.elektrik}, {"ay": 2, "tutar_kurus": -1, "kategori": self.elektrik}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                GenelGider.objects.create(**{"kategori": self.kira, "yil": 2026, "ay": 1, "tutar_kurus": 5, **kw})

    def test_pasif_kategori_veri_varsa_tabloda_kalir(self):
        self.g(self.personel, 2026, 3, 500)
        self.personel.aktif = False
        self.personel.save()
        self.assertIn(self.personel, gs.kategoriler_yil(2026))
        self.assertNotIn(self.personel, gs.kategoriler_yil(2027))


class ServisTests(Temel):
    def test_yillik_tablo_toplamlari(self):
        self.g(self.kira, 2026, 1, 10000)
        self.g(self.kira, 2026, 2, 10000)
        self.g(self.elektrik, 2026, 2, 2550)
        self.g(self.kira, 2025, 12, 99999)                      # başka yıl karışmaz
        t = gs.yillik_tablo(2026)
        self.assertEqual(t["ay_toplam"][:3], [10000, 12550, 0])
        self.assertEqual(t["kat_toplam"][self.kira.pk], 20000)
        self.assertEqual(t["toplam"], 22550)
        satir = [r for r in t["satirlar"] if r["kategori"] == self.kira][0]
        self.assertEqual((satir["aylar"][0], satir["aylar"][2], satir["toplam"]), (10000, 0, 20000))

    def test_ozet(self):
        self.g(self.kira, 2026, 1, 10000)
        self.g(self.kira, 2026, 2, 10000)
        self.g(self.elektrik, 2026, 2, 2000)
        self.g(self.personel, 2026, 3, 50000)
        o = gs.ozet(2026, 3)
        self.assertEqual((o["secili"], o["onceki"], o["ytd"]), (50000, 12000, 72000))
        self.assertEqual(o["degisim"], {"yon": "yukari", "yuzde": 317})
        self.assertEqual((o["ortalama"], o["dolu_ay"]), (24000, 3))
        self.assertEqual(o["en_buyuk"][1], self.personel)

    def test_ocakta_onceki_ay_gecen_yilin_aralik_ayi(self):
        self.g(self.kira, 2025, 12, 8000)
        self.g(self.kira, 2026, 1, 10000)
        self.assertEqual(gs.ozet(2026, 1)["onceki"], 8000)
        self.assertEqual(gs.onceki_ay(2026, 1), (2025, 12))

    def test_bos_yil_ozeti(self):
        o = gs.ozet(2030, 5)
        self.assertEqual((o["secili"], o["ytd"], o["ortalama"], o["en_buyuk"], o["degisim"]), (0, 0, 0, None, None))

    def test_ortalama_bos_aylari_saymaz(self):
        self.g(self.kira, 2026, 1, 1000)
        self.g(self.kira, 2026, 4, 3000)                        # şubat-mart girilmedi
        o = gs.ozet(2026, 4)
        self.assertEqual((o["ortalama"], o["dolu_ay"]), (2000, 2))

    def test_kaydet_olusturur_gunceller_sifirlar_degismeyene_dokunmaz(self):
        kats = [self.kira, self.elektrik]
        self.assertEqual(gs.kaydet(2026, 5, {f"tutar_{self.kira.pk}": "12.500,00", f"not_{self.kira.pk}": "mayıs",
                                              f"tutar_{self.elektrik.pk}": ""}, kats), 1)
        g = GenelGider.objects.get(kategori=self.kira, yil=2026, ay=5)
        self.assertEqual((g.tutar_kurus, g.aciklama), (1250000, "mayıs"))
        self.assertFalse(GenelGider.objects.filter(kategori=self.elektrik).exists())    # boş ve kayıt yok: oluşturulmaz
        n_gunluk = IslemGunlugu.objects.count()
        self.assertEqual(gs.kaydet(2026, 5, {f"tutar_{self.kira.pk}": "12.500,00", f"not_{self.kira.pk}": "mayıs"}, kats), 0)
        self.assertEqual(IslemGunlugu.objects.count(), n_gunluk)                       # değişmedi: günlük şişmez
        self.assertEqual(gs.kaydet(2026, 5, {f"tutar_{self.kira.pk}": "13.000,00"}, kats), 1)
        self.assertEqual(gs.kaydet(2026, 5, {f"tutar_{self.kira.pk}": ""}, kats), 1)    # boş: sıfırlanır, silinmez
        g.refresh_from_db()
        self.assertEqual(g.tutar_kurus, 0)

    def test_kaydet_hata_varsa_hicbiri_kaydedilmez(self):
        kats = [self.kira, self.elektrik]
        with self.assertRaises(ValidationError) as e:
            gs.kaydet(2026, 5, {f"tutar_{self.kira.pk}": "1.000,00", f"tutar_{self.elektrik.pk}": "12.5.0"}, kats)
        self.assertIn("Elektrik", " ".join(e.exception.messages))
        self.assertEqual(GenelGider.objects.count(), 0)

    def test_eksi_ve_belirsiz_tutar_reddedilir(self):
        for v in ("-100,00", "1234.50", "abc"):
            with self.assertRaises(ValidationError, msg=v):
                gs.kaydet(2026, 5, {f"tutar_{self.kira.pk}": v}, [self.kira])
        self.assertEqual(GenelGider.objects.count(), 0)

    def test_gecersiz_ay(self):
        with self.assertRaises(ValidationError):
            gs.kaydet(2026, 13, {}, [self.kira])

    def test_degisiklik_islem_gunlugune_yazilir(self):
        self.g(self.kira, 2026, 1, 10000)
        gs.kaydet(2026, 1, {f"tutar_{self.kira.pk}": "110,00"}, [self.kira])
        g = IslemGunlugu.objects.filter(model="GenelGider", islem="DEGISTI").first()
        self.assertIsNotNone(g)
        self.assertEqual(g.degisiklik["Net tutar, KDV hariç (₺)"], ["100,00 ₺", "110,00 ₺"])

    def test_onceki_aydan_kopyala_yalniz_bos_satirlari_doldurur(self):
        self.g(self.kira, 2026, 1, 10000, "kira")
        self.g(self.elektrik, 2026, 1, 3000)
        self.g(self.personel, 2026, 1, 50000)
        self.g(self.elektrik, 2026, 2, 3500)                    # dolu: dokunulmaz
        self.g(self.personel, 2026, 2, 0)                       # sıfır: doldurulur
        n = gs.onceki_aydan_kopyala(2026, 2, [self.kira, self.elektrik, self.personel])
        self.assertEqual(n, 2)
        al = lambda k: GenelGider.objects.get(kategori=k, yil=2026, ay=2)
        self.assertEqual((al(self.kira).tutar_kurus, al(self.kira).aciklama), (10000, "kira"))
        self.assertEqual(al(self.elektrik).tutar_kurus, 3500)
        self.assertEqual(al(self.personel).tutar_kurus, 50000)

    def test_ocaktan_kopyalama_gecen_yil_araligi_alir(self):
        self.g(self.kira, 2025, 12, 7000)
        self.assertEqual(gs.onceki_aydan_kopyala(2026, 1, [self.kira]), 1)
        self.assertEqual(GenelGider.objects.get(yil=2026, ay=1).tutar_kurus, 7000)

    def test_xlsx_degerler_ve_toplam(self):
        self.g(self.kira, 2026, 1, 123456)
        self.g(self.elektrik, 2026, 3, 100)
        ws = openpyxl.load_workbook(BytesIO(gs.yillik_xlsx(2026))).active
        satir = {ws.cell(row=r, column=1).value: [c.value for c in ws[r]] for r in range(4, 12)}
        self.assertEqual(float(satir["Kira"][1]), 1234.56)
        self.assertEqual(float(satir["Kira"][13]), 1234.56)
        self.assertEqual(float(satir["NET GENEL GİDER"][13]), 1235.56)
        self.assertEqual(float(satir["NET GENEL GİDER"][3]), 1.0)


class EkranTests(Temel):
    def setUp(self):
        super().setUp()
        self.url = reverse("giderler")
        self.muh = rol_kullanici("m", "Muhasebe")
        self.client.force_login(self.muh)

    def test_sayfa_acilir_kartlar_ve_form(self):
        self.g(self.kira, 2026, 3, 1250000)
        r = self.client.get(self.url, {"yil": 2026, "ay": 3})
        self.assertEqual(r.status_code, 200)
        for parca in ("Mart net genel gider", "12.500,00", "Yıl başından Mart sonuna", "Aylık ortalama", "En büyük kalem",
                      'name="tutar_%d"' % self.kira.pk, "Önceki aydan kopyala", "Yeni kategori", "yıllık tablo"):
            self.assertContains(r, parca)
        self.assertEqual(r.content.decode().count("<h1"), 1)

    def test_varsayilan_ay_ve_gecersiz_parametreler_cokmez(self):
        for q in ({}, {"yil": "x"}, {"ay": "99"}, {"yil": "1900", "ay": "0"}, {"yil": "2026", "ay": "abc"}):
            self.assertEqual(self.client.get(self.url, q).status_code, 200, q)
        r = self.client.get(self.url, {"yil": "2025"})
        self.assertEqual(r.context["ay"], 12)                  # geçmiş yılda aralık
        r = self.client.get(self.url)
        self.assertEqual((r.context["yil"], r.context["ay"]), (date.today().year, date.today().month))

    def test_kaydet_ve_yonlendir(self):
        r = self.client.post(f"{self.url}?yil=2026&ay=4", {"eylem": "kaydet", f"tutar_{self.kira.pk}": "9.000,00",
                                                           f"tutar_{self.personel.pk}": "85.000,00"})
        self.assertRedirects(r, f"{self.url}?yil=2026&ay=4")
        self.assertEqual(GenelGider.objects.get(kategori=self.kira, yil=2026, ay=4).tutar_kurus, 900000)
        r = self.client.get(self.url, {"yil": 2026, "ay": 4})
        self.assertEqual(r.context["ozet"]["secili"], 9400000)
        self.assertContains(r, "94.000,00")

    def test_hatali_giris_formu_girdilerle_geri_getirir(self):
        r = self.client.post(f"{self.url}?yil=2026&ay=4", {f"tutar_{self.kira.pk}": "9.000,00", f"tutar_{self.elektrik.pk}": "xx"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Elektrik: tutarı 1.234,50 biçiminde girin.")
        self.assertContains(r, 'value="9.000,00"')              # yazılanlar kaybolmaz
        self.assertEqual(GenelGider.objects.count(), 0)

    def test_kopyala_eylemi(self):
        self.g(self.kira, 2026, 3, 10000)
        r = self.client.post(f"{self.url}?yil=2026&ay=4", {"eylem": "kopyala"}, follow=True)
        self.assertContains(r, "1 kalem kopyalandı")
        self.assertEqual(GenelGider.objects.get(yil=2026, ay=4).tutar_kurus, 10000)
        r = self.client.post(f"{self.url}?yil=2026&ay=4", {"eylem": "kopyala"}, follow=True)
        self.assertContains(r, "Kopyalanacak kalem yok")

    def test_excel_indir(self):
        self.g(self.kira, 2026, 1, 100)
        r = self.client.get(self.url, {"yil": 2026, "indir": "xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.assertIn("genel_gider_2026.xlsx", r["Content-Disposition"])

    def test_kategori_ekle(self):
        r = self.client.post(reverse("gider_kategori_ekle"), {"ad": "  Sigorta  ", "yil": 2026, "ay": 5}, follow=True)
        self.assertContains(r, "kategorisi eklendi")
        self.assertTrue(GiderKategori.objects.filter(ad="Sigorta").exists())
        self.assertContains(self.client.get(self.url), "Sigorta")

    def test_kategori_tekrari_turkce_duyarsiz_reddedilir(self):
        for ad in ("kira", "KİRA", "Mali Musavir", "  "):
            r = self.client.post(reverse("gider_kategori_ekle"), {"ad": ad}, follow=True)
            self.assertEqual(GiderKategori.objects.count(), 7, ad)

    def test_kategori_get_ile_eklenmez(self):
        self.assertEqual(self.client.get(reverse("gider_kategori_ekle"), {"ad": "X"}).status_code, 405)

    def test_html_kacar(self):
        k = GiderKategori.objects.create(ad="<b>x</b>")
        self.g(k, 2026, 1, 100, "<script>y</script>")
        h = self.client.get(self.url, {"yil": 2026, "ay": 1}).content.decode()
        self.assertNotIn("<script>y</script>", h)
        self.assertNotIn("<b>x</b>", h)

    def test_menu_baglantisi(self):
        self.assertContains(self.client.get(self.url), 'aria-current="page"')
        self.assertContains(self.client.get(reverse("dashboard")), reverse("giderler"))


class YetkiTests(Temel):
    def setUp(self):
        super().setUp()
        self.url = reverse("giderler")

    def test_goruntuleyici_gorur_yazamaz(self):
        self.g(self.kira, 2026, 1, 100000)
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        r = self.client.get(self.url, {"yil": 2026, "ay": 1})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "1.000,00")
        for yok in ("Önceki aydan kopyala", "Yeni kategori", 'name="tutar_'):
            self.assertNotContains(r, yok)
        self.assertEqual(self.client.post(f"{self.url}?yil=2026&ay=1", {f"tutar_{self.kira.pk}": "5,00"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("gider_kategori_ekle"), {"ad": "X"}).status_code, 403)
        self.assertEqual(GenelGider.objects.get().tutar_kurus, 100000)

    def test_kasiyer_ve_rolsuz_goremez(self):
        for ad, rol in (("k", "Kasiyer"), ("r", None)):
            self.client.force_login(rol_kullanici(ad, rol))
            self.assertEqual(self.client.get(self.url).status_code, 403, ad)
            self.assertEqual(self.client.get(self.url, {"indir": "xlsx"}).status_code, 403, ad)

    def test_giris_gerekli(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])

    def test_menude_kasiyere_gorunmez(self):
        self.client.force_login(rol_kullanici("k", "Kasiyer"))
        self.assertNotContains(self.client.get(reverse("kasa")), reverse("giderler"))

    def test_muhasebe_panelde_gider_ekleyebilir_silemez(self):
        m = rol_kullanici("m", "Muhasebe")
        self.client.force_login(m)
        self.assertEqual(self.client.get(reverse("admin:defter_genelgider_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:defter_giderkategori_changelist")).status_code, 200)
        g = self.g(self.kira, 2026, 1, 100)
        self.assertEqual(self.client.get(reverse("admin:defter_genelgider_delete", args=[g.pk])).status_code, 403)
