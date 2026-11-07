"""Aylık özet raporu: hesaplar, tutarlılık (bakiye denklemi), ekran, Excel, yetki."""
from datetime import date
from io import BytesIO

import openpyxl
from django.test import TestCase
from django.urls import reverse

from . import rapor_servisi as rs
from .models import Belge, Cari, GenelGider, GiderKategori, Hesap, KasaHareketi, KasaKategori
from .test_yardimci import rol_kullanici


class Temel(TestCase):
    def setUp(self):
        self.a = Cari.objects.create(unvan="A Ltd")
        self.b = Cari.objects.create(unvan="B Ltd")
        self.ofis = Hesap.objects.get(ad="Ofis Kasa")

    def belge(self, cari, tur, tarih, tutar, iptal=False):
        return Belge.objects.create(cari=cari, tur=tur, tarih=tarih, tutar_kurus=tutar, iptal=iptal, iptal_nedeni="x" if iptal else "")


class RaporServisTests(Temel):
    def veri(self):
        self.belge(self.a, "ACILIS", date(2026, 1, 1), 10000)
        self.belge(self.a, "ALIS_FISI", date(2026, 3, 5), 5000)        # mart
        self.belge(self.a, "ALIS_FATURASI", date(2026, 3, 20), 3000)
        self.belge(self.a, "ODEME", date(2026, 3, 25), 4000)
        self.belge(self.a, "IADE", date(2026, 3, 26), 500)
        self.belge(self.a, "DUZELTME_ARTI", date(2026, 3, 27), 200)
        self.belge(self.a, "DUZELTME_EKSI", date(2026, 3, 28), 50)
        self.belge(self.b, "ALIS_FISI", date(2026, 3, 10), 700)
        self.belge(self.a, "ALIS_FISI", date(2026, 4, 2), 9999)        # sonraki ay: karışmaz
        self.belge(self.a, "ALIS_FISI", date(2026, 3, 11), 8888, iptal=True)   # iptal: karışmaz

    def test_toplamlar_ve_bakiye_denklemi(self):
        self.veri()
        r = rs.aylik_rapor(2026, 3)
        a = [s for s in r["tedarikciler"] if s["cari"] == self.a][0]
        self.assertEqual((a["alis"], a["iade"], a["odeme"], a["diger"]), (8000, 500, 4000, 150))
        self.assertEqual((a["acilis"], a["kapanis"]), (10000, 10000 + 8000 - 500 - 4000 + 150))
        for s in r["tedarikciler"]:                                  # her satırda denklem tutar
            self.assertEqual(s["acilis"] + s["alis"] + s["diger"] - s["iade"] - s["odeme"], s["kapanis"], s["cari"])
        t = r["ted_toplam"]
        self.assertEqual(t["acilis"] + t["alis"] + t["diger"] - t["iade"] - t["odeme"], t["kapanis"])
        self.assertEqual((t["alis"], t["odeme"]), (8700, 4000))

    def test_ay_sonu_borc_ve_avans(self):
        self.belge(self.a, "ALIS_FISI", date(2026, 3, 1), 1000)
        self.belge(self.b, "ODEME", date(2026, 3, 2), 400)               # fazla ödeme
        r = rs.aylik_rapor(2026, 3)
        self.assertEqual((r["ay_sonu_borc"], r["ay_sonu_avans"]), (1000, 400))

    def test_hareketsiz_ve_sifir_bakiyeli_cari_listelenmez(self):
        self.belge(self.a, "ALIS_FISI", date(2026, 3, 1), 100)
        self.belge(self.a, "ODEME", date(2026, 3, 2), 100)               # sıfırlandı ama ay içinde hareketi var
        r = rs.aylik_rapor(2026, 3)
        self.assertEqual([s["cari"] for s in r["tedarikciler"]], [self.a])
        self.assertEqual(rs.aylik_rapor(2026, 6)["tedarikciler"], [])    # b hiç hareket görmemiş, a bakiyesi 0

    def test_ocak_onceki_ay_gecen_yil(self):
        self.belge(self.a, "ALIS_FISI", date(2025, 12, 5), 1000)
        self.belge(self.a, "ALIS_FISI", date(2026, 1, 5), 1500)
        r = rs.aylik_rapor(2026, 1)
        self.assertEqual(r["ted_degisim"]["alis"], {"yon": "yukari", "yuzde": 50})
        self.assertEqual(r["ted_toplam"]["acilis"], 1000)

    def test_genel_gider_kalemleri_ve_ozet(self):
        kira, el = GiderKategori.objects.get(ad="Kira"), GiderKategori.objects.get(ad="Elektrik")
        GenelGider.objects.create(kategori=kira, yil=2026, ay=3, tutar_kurus=10000)
        GenelGider.objects.create(kategori=el, yil=2026, ay=3, tutar_kurus=2000)
        GenelGider.objects.create(kategori=kira, yil=2026, ay=2, tutar_kurus=9000)
        r = rs.aylik_rapor(2026, 3)
        self.assertEqual([(k.ad, v) for k, v in r["gider_kalemleri"]], [("Kira", 10000), ("Elektrik", 2000)])
        self.assertEqual((r["gider"]["secili"], r["gider"]["ytd"]), (12000, 21000))

    def test_kasa_ay_ozeti_kategoriler_ve_kapanis(self):
        kat = KasaKategori.objects.create(ad="Kırtasiye")
        KasaHareketi.objects.create(hesap=self.ofis, yon="GIRIS", tarih=date(2026, 2, 28), tutar_kurus=50000)   # önceki ay
        KasaHareketi.objects.create(hesap=self.ofis, yon="GIRIS", tarih=date(2026, 3, 2), tutar_kurus=10000)
        KasaHareketi.objects.create(hesap=self.ofis, yon="CIKIS", tarih=date(2026, 3, 3), tutar_kurus=2500, kategori=kat)
        KasaHareketi.objects.create(hesap=self.ofis, yon="CIKIS", tarih=date(2026, 3, 4), tutar_kurus=500)
        KasaHareketi.objects.create(hesap=self.ofis, yon="CIKIS", tarih=date(2026, 3, 5), tutar_kurus=9999, iptal=True, iptal_nedeni="x")
        KasaHareketi.objects.create(hesap=self.ofis, yon="CIKIS", tarih=date(2026, 4, 1), tutar_kurus=1)         # sonraki ay
        k = rs.aylik_rapor(2026, 3)["kasa"][0]
        self.assertEqual((k["giris"], k["cikis"], k["kapanis"]), (10000, 3000, 57000))
        self.assertEqual(k["kategoriler"], [("Kırtasiye", 2500), ("Kategorisiz", 500)])

    def test_kasa_yetkisiz_dahil_edilmez(self):
        self.assertIsNone(rs.aylik_rapor(2026, 3, kasa_dahil=False)["kasa"])

    def test_bos_ay_cokmez(self):
        r = rs.aylik_rapor(2030, 7)
        self.assertEqual((r["ted_toplam"]["alis"], r["gider"]["secili"], r["ay_sonu_borc"]), (0, 0, 0))

    def test_xlsx_degerleri(self):
        self.veri()
        GenelGider.objects.create(kategori=GiderKategori.objects.get(ad="Kira"), yil=2026, ay=3, tutar_kurus=123456)
        wb = openpyxl.load_workbook(BytesIO(rs.rapor_xlsx(rs.aylik_rapor(2026, 3))))
        self.assertEqual(wb.sheetnames, ["Özet", "Tedarikçiler", "Genel gider", "Kasa"])
        ozet = {c[0].value: c[1].value for c in wb["Özet"].iter_rows(min_row=3, max_row=8)}
        self.assertEqual(float(ozet["Net genel gider (KDV hariç)"]), 1234.56)
        self.assertEqual(float(ozet["Tedarikçi alışları"]), 87.0)
        ted = {r[0].value: [c.value for c in r] for r in wb["Tedarikçiler"].iter_rows(min_row=2)}
        self.assertEqual(float(ted["TOPLAM"][2]), 87.0)


class RaporEkranTests(Temel):
    def setUp(self):
        super().setUp()
        self.url = reverse("aylik_rapor")
        self.belge(self.a, "ALIS_FISI", date(2026, 3, 5), 123450)
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))

    def test_sayfa(self):
        r = self.client.get(self.url, {"yil": 2026, "ay": 3})
        self.assertEqual(r.status_code, 200)
        for p in ("Aylık rapor: Mart 2026", "1.234,50", "A Ltd", "Tedarikçi hareketleri", "Net genel gider", "Ofis Kasa", "Yazdır / PDF"):
            self.assertContains(r, p)
        self.assertEqual(r.content.decode().count("<h1"), 1)

    def test_varsayilan_onceki_tam_ay_ve_gecersiz_parametreler(self):
        bugun = date.today()
        beklenen = (bugun.year - 1, 12) if bugun.month == 1 else (bugun.year, bugun.month - 1)
        r = self.client.get(self.url)
        self.assertEqual((r.context["yil"], r.context["ay"]), beklenen)
        for q in ({"yil": "x"}, {"ay": "13"}, {"yil": "1800", "ay": "1"}, {"ay": "0"}):
            self.assertEqual(self.client.get(self.url, q).status_code, 200, q)

    def test_excel(self):
        r = self.client.get(self.url, {"yil": 2026, "ay": 3, "indir": "xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("aylik_ozet_2026_03.xlsx", r["Content-Disposition"])

    def test_yetki(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        for ad, rol in (("k", "Kasiyer"), ("r", None)):
            self.client.force_login(rol_kullanici(ad, rol))
            self.assertEqual(self.client.get(self.url).status_code, 403, ad)
            self.assertEqual(self.client.get(self.url, {"indir": "xlsx"}).status_code, 403, ad)
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_html_kacar(self):
        c = Cari.objects.create(unvan="<script>w</script>")
        self.belge(c, "ALIS_FISI", date(2026, 3, 6), 100)
        self.assertNotContains(self.client.get(self.url, {"yil": 2026, "ay": 3}), "<script>w</script>")

    def test_menu_baglantisi(self):
        self.assertContains(self.client.get(self.url), 'aria-current="page"')


class GecenYilKarsilastirmaTests(TestCase):
    def test_gecen_yilin_ayni_ayi(self):
        from . import rapor_servisi as rs
        from .models import GenelGider, GiderKategori
        kira = GiderKategori.objects.get(ad="Kira")
        GenelGider.objects.create(kategori=kira, yil=2025, ay=6, tutar_kurus=10000)
        GenelGider.objects.create(kategori=kira, yil=2026, ay=6, tutar_kurus=15000)
        r = rs.aylik_rapor(2026, 6)
        ad, bu, gy, d = next(x for x in r["gecen_yil"] if x[0] == "Net genel gider")
        self.assertEqual((bu, gy, d["yon"], d["yuzde"]), (15000, 10000, "yukari", 50))

    def test_gecen_yil_verisi_yoksa_bolum_gizli(self):
        from . import rapor_servisi as rs
        self.assertIsNone(rs.aylik_rapor(2026, 6)["gecen_yil"])
