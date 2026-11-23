"""Gösterge kartı yardımcıları: değişim yüzdesi, sparkline, avatar, 'önceki aya göre' etiketi."""
from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import trend
from .models import Belge, Cari
from .templatetags.defter_filtreleri import avatar, bas_harfler, degisim_etiketi, sparkline
from .test_yardimci import rol_kullanici

BUGUN = date(2026, 6, 15)       # Haziran süren ay; son tam ay Mayıs (indeks 4), öncesi Nisan (3)


class SonTamAyTests(SimpleTestCase):
    def test_gecmis_yil_aralik_gelecek_yil_yok(self):
        self.assertEqual(trend.son_tam_ay_indeksi(2025, BUGUN), 11)
        self.assertEqual(trend.son_tam_ay_indeksi(2026, BUGUN), 4)
        self.assertEqual(trend.son_tam_ay_indeksi(2027, BUGUN), -1)

    def test_ocakta_tam_ay_yok(self):
        self.assertEqual(trend.son_tam_ay_indeksi(2026, date(2026, 1, 10)), -1)
        self.assertEqual(trend.son_tam_ay_indeksi(2026, date(2026, 2, 10)), 0)


class DegisimTests(SimpleTestCase):
    def seri(self, nisan, mayis, haziran=999):
        s = [0] * 12
        s[3], s[4], s[5] = nisan, mayis, haziran
        return s

    def test_artis_azalis_yatay(self):
        self.assertEqual(trend.degisim(self.seri(100, 150), 2026, BUGUN), {"yon": "yukari", "yuzde": 50})
        self.assertEqual(trend.degisim(self.seri(200, 150), 2026, BUGUN), {"yon": "asagi", "yuzde": 25})
        self.assertEqual(trend.degisim(self.seri(100, 100), 2026, BUGUN), {"yon": "yatay", "yuzde": 0})

    def test_suren_ay_hesaba_katilmaz(self):
        """Haziran (süren) değeri ne olursa olsun sonuç Mayıs/Nisan'a göre."""
        self.assertEqual(trend.degisim(self.seri(100, 150, 1), 2026, BUGUN), trend.degisim(self.seri(100, 150, 10**9), 2026, BUGUN))

    def test_onceki_ay_sifirsa_yuzde_yok_yon_var(self):
        self.assertEqual(trend.degisim(self.seri(0, 50), 2026, BUGUN), {"yon": "yukari", "yuzde": None})

    def test_cok_kucuk_degisim_sifir_yuzde_gostermez(self):
        self.assertEqual(trend.degisim(self.seri(100000, 100001), 2026, BUGUN)["yuzde"], 1)

    def test_eksik_veri_none(self):
        self.assertIsNone(trend.degisim([None] * 12, 2026, BUGUN))
        self.assertIsNone(trend.degisim([1] * 12, 2027, BUGUN))
        self.assertIsNone(trend.degisim([1] * 12, 2026, date(2026, 2, 1)))     # yalnızca 1 tam ay: kıyas yok

    def test_eksi_onceki_deger_mutlak_tabanla(self):
        self.assertEqual(trend.degisim(self.seri(-100, -50), 2026, BUGUN), {"yon": "yukari", "yuzde": 50})


class SparklineTests(SimpleTestCase):
    def test_az_nokta_none(self):
        self.assertIsNone(trend.sparkline_yollari([5]))
        self.assertIsNone(trend.sparkline_yollari([None, None, 4]))

    def test_nokta_sayisi_ve_none_atlanir(self):
        cizgi, alan = trend.sparkline_yollari([1, None, 3, 2, None])
        self.assertEqual(cizgi.count("L") + 1, 3)
        self.assertTrue(alan.endswith("Z"))

    def test_en_yuksek_deger_en_ustte(self):
        cizgi, _ = trend.sparkline_yollari([0, 10])
        (x0, y0), (x1, y1) = [tuple(map(float, p.replace("M", "").split())) for p in cizgi.split(" L")]
        self.assertGreater(y0, y1)           # SVG'de küçük y = yukarı
        self.assertLessEqual(max(y0, y1), 32)
        self.assertGreaterEqual(min(y0, y1), 0)

    def test_sabit_seri_ortada_duz(self):
        cizgi, _ = trend.sparkline_yollari([7, 7, 7])
        ys = {p.split()[-1] for p in cizgi.replace("M", "").split(" L")}
        self.assertEqual(ys, {"16.0"})

    def test_etiket_cikti_svg_ve_dekoratif(self):
        h = str(sparkline([1, 2, 3]))
        self.assertIn("<svg", h)
        self.assertIn('aria-hidden="true"', h)
        self.assertEqual(str(sparkline([1])), "")


class AvatarTests(SimpleTestCase):
    def test_bas_harfler_turkce(self):
        self.assertEqual(bas_harfler("Eröz Hırdavat Ltd."), "EH")
        self.assertEqual(bas_harfler("işçi ilaç"), "İİ")          # i -> İ (Türkçe), I'ya dönmez
        self.assertEqual(bas_harfler("ışık"), "IŞ")
        self.assertEqual(bas_harfler("Demir"), "DE")
        self.assertEqual(bas_harfler(""), "?")
        self.assertEqual(bas_harfler(None), "?")

    def test_renk_sabit_ve_aralikta(self):
        a = str(avatar("Eröz Hırdavat")); b = str(avatar("Eröz Hırdavat"))
        self.assertEqual(a, b)
        import re
        for ad in ("A", "B", "Çelik Sanayi", "x" * 40):
            self.assertRegex(str(avatar(ad)), r'av-[1-8] ')

    def test_ad_html_kacar(self):
        self.assertNotIn("<script", str(avatar("<script>alert(1)</script>")))


class DegisimEtiketiTests(SimpleTestCase):
    def test_bos_veri_bos_etiket(self):
        self.assertEqual(str(degisim_etiketi(None)), "")

    def test_ton_iyi_kotu(self):
        yukari = {"yon": "yukari", "yuzde": 12}
        asagi = {"yon": "asagi", "yuzde": 12}
        self.assertIn("degisim kotu", str(degisim_etiketi(yukari, "yuksek_kotu")))     # borç arttı = kötü
        self.assertIn("degisim iyi", str(degisim_etiketi(asagi, "yuksek_kotu")))
        self.assertIn("degisim iyi", str(degisim_etiketi(yukari, "yuksek_iyi")))
        self.assertIn("degisim kotu", str(degisim_etiketi(asagi, "yuksek_iyi")))

    def test_notr_ve_yatay_renksiz(self):
        for d, ton in (({"yon": "yukari", "yuzde": 5}, "notr"), ({"yon": "yatay", "yuzde": 0}, "yuksek_kotu")):
            h = str(degisim_etiketi(d, ton))
            self.assertNotIn(" iyi", h)
            self.assertNotIn(" kotu", h)

    def test_yon_renge_ek_olarak_metinle_de_soylenir(self):
        h = str(degisim_etiketi({"yon": "yukari", "yuzde": 12}, "yuksek_kotu"))
        self.assertIn("%12", h)
        self.assertIn("yüzde 12 artış", h)
        self.assertIn("önceki aya göre", h)
        self.assertIn("#i-ok-yukari", h)
        self.assertIn('class="sr-only"', h)       # metin görünmez ama ekran okuyucuya okunur
        from .test_arayuz import CSS
        self.assertIn(".sr-only {", CSS)             # sınıfın stili gerçekten tanımlı


class DashboardKartTests(TestCase):
    def test_dashboard_sparkline_ve_degisim_gosterir(self):
        cari = Cari.objects.create(unvan="Deneme Tedarik")
        # önceki yılın tam ayları: değişim hesaplanabilsin
        for ay, tutar in ((10, 100000), (11, 150000)):
            Belge.objects.create(cari=cari, tur=Belge.Tur.ALIS_FISI, tarih=date(2025, ay, 5), tutar_kurus=tutar)
        k = rol_kullanici("yon", is_superuser=True)
        self.client.force_login(k)
        h = self.client.get(reverse("dashboard"), {"yil": 2025}).content.decode()
        self.assertIn("sparkline", h)
        self.assertIn("kpi-ikon", h)
        self.assertIn("avatar", h)                    # kenar çubuğundaki kullanıcı

    def test_yetkisiz_kart_markup_bozmaz_bos_veri(self):
        k = rol_kullanici("yon", is_superuser=True)
        self.client.force_login(k)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
