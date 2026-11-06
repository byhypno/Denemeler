from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import odeme_listesi as ol
from . import services
from .models import Belge, Cari
from .test_yardimci import rol_kullanici


class ListeTemel(TestCase):
    def setUp(self):
        self.a = Cari.objects.create(unvan="A TEDARİK", vade_gun=30)
        self.b = Cari.objects.create(unvan="B TEDARİK")
        self.c = Cari.objects.create(unvan="C AVANS")

    def belge(self, cari, tur, tutar, tarih, no="", **kw):
        return Belge.objects.create(cari=cari, tur=tur, tutar_kurus=tutar, tarih=tarih, evrak_no=no, **kw)


class OdenecekHesapTests(ListeTemel):
    def test_toplam_cari_bakiyelerinin_pozitif_toplamina_esit(self):
        self.belge(self.a, "ALIS_FISI", 100000, date(2026, 1, 1), "1")
        self.belge(self.a, "ODEME", 30000, date(2026, 1, 5))
        self.belge(self.b, "ALIS_FISI", 50000, date(2026, 2, 1), "2")
        self.belge(self.c, "ODEME", 7000, date(2026, 2, 2))            # avans
        v = ol.odenecekler(date(2026, 3, 1))
        pozitif = sum(b for _, b in services.cari_bakiyeleri() if b > 0)
        self.assertEqual(v["toplam_kurus"], pozitif)
        self.assertEqual(v["toplam_kurus"], 70000 + 50000)
        self.assertEqual([r["cari"].unvan for r in v["satirlar"]], ["A TEDARİK", "B TEDARİK"])   # büyükten küçüğe
        self.assertEqual(sum(v["kovalar"]), v["toplam_kurus"])
        self.assertEqual([(c.unvan, t) for c, t in v["avanslar"]], [("C AVANS", 7000)])

    def test_satir_ayrintilari_ve_kovalar(self):
        self.belge(self.a, "ALIS_FISI", 100, date(2026, 1, 1), "1")      # 59 gün -> 31–60
        self.belge(self.a, "ALIS_FISI", 200, date(2026, 2, 28), "2")     # 1 gün -> 0–30
        v = ol.odenecekler(date(2026, 3, 1))
        s = v["satirlar"][0]
        self.assertEqual(s["kovalar"], [200, 100, 0, 0])
        self.assertEqual((s["en_eski_tarih"], s["en_eski_yas"], s["kalem_sayisi"]), (date(2026, 1, 1), 59, 2))
        self.assertTrue(s["vade_tanimli"])
        self.assertEqual(s["vadesi_gecmis_kurus"], 100)                   # yalnızca 1 Oca'nın vadesi (30 gün) geçti

    def test_borcu_kapanan_cari_listede_yok(self):
        self.belge(self.a, "ALIS_FISI", 500, date(2026, 1, 1), "1")
        self.belge(self.a, "ODEME", 500, date(2026, 1, 2))
        self.assertEqual(ol.odenecekler(date(2026, 3, 1))["satirlar"], [])

    def test_cari_filtresi(self):
        self.belge(self.a, "ALIS_FISI", 500, date(2026, 1, 1), "1")
        self.belge(self.b, "ALIS_FISI", 700, date(2026, 1, 1), "2")
        v = ol.odenecekler(date(2026, 3, 1), cari=self.b)
        self.assertEqual([r["cari"] for r in v["satirlar"]], [self.b])
        self.assertEqual(v["toplam_kurus"], 700)

    def test_iptal_sayilmaz(self):
        self.belge(self.a, "ALIS_FISI", 500, date(2026, 1, 1), "1", iptal=True, iptal_nedeni="x")
        self.assertEqual(ol.odenecekler(date(2026, 3, 1))["satirlar"], [])


class YapilanOdemelerTests(ListeTemel):
    def setUp(self):
        super().setUp()
        self.belge(self.a, "ODEME", 10000, date(2026, 1, 10), odeme_sekli="HAVALE", aciklama="Ocak")
        self.belge(self.a, "ODEME", 5000, date(2026, 2, 10), odeme_sekli="NAKIT")
        self.belge(self.b, "ODEME", 7000, date(2026, 1, 20), odeme_sekli="NAKIT")
        self.belge(self.b, "ALIS_FISI", 99999, date(2026, 1, 20), "1")                 # ödeme değil
        self.belge(self.b, "IADE", 8888, date(2026, 1, 21), "2")                         # ödeme değil
        self.belge(self.b, "ODEME", 3333, date(2026, 1, 22), iptal=True, iptal_nedeni="x")

    def test_donem_toplami_ve_gruplama(self):
        v = ol.yapilan_odemeler(date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(v["toplam_kurus"], 17000)
        self.assertEqual(v["adet"], 2)
        self.assertEqual([(g["cari"].unvan, g["toplam_kurus"]) for g in v["gruplar"]],
                         [("A TEDARİK", 10000), ("B TEDARİK", 7000)])

    def test_tum_donem_ve_sekil_toplamlari(self):
        v = ol.yapilan_odemeler(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(v["toplam_kurus"], 22000)
        self.assertEqual(dict(v["sekil_toplamlari"]), {"Nakit": 12000, "Havale/EFT": 10000})

    def test_filtreler(self):
        bas, bit = date(2026, 1, 1), date(2026, 12, 31)
        self.assertEqual(ol.yapilan_odemeler(bas, bit, cari=self.a)["toplam_kurus"], 15000)
        self.assertEqual(ol.yapilan_odemeler(bas, bit, sekil="NAKIT")["toplam_kurus"], 12000)
        self.assertEqual(ol.yapilan_odemeler(date(2026, 1, 10), date(2026, 1, 10))["toplam_kurus"], 10000)  # sınır dahil
        self.assertEqual(ol.yapilan_odemeler(date(2027, 1, 1), date(2027, 1, 2))["gruplar"], [])


def D(x):
    """xlsx sayıları dosyadan float okunur; kuruşlu değeri tam karşılaştırmak için Decimal'e çevir."""
    return Decimal(str(x))


class ExcelCiktiTests(ListeTemel):
    def yukle(self, veri_baytlari):
        return openpyxl.load_workbook(BytesIO(veri_baytlari))

    def test_odenecekler_xlsx_degerleri_tam_kurus(self):
        self.belge(self.a, "ALIS_FISI", 123456, date(2026, 1, 1), "1")
        self.belge(self.b, "ALIS_FISI", 65, date(2026, 1, 1), "2")
        ws = self.yukle(ol.odenecekler_xlsx(ol.odenecekler(date(2026, 1, 31)))).active
        satirlar = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(5, 9)}
        self.assertEqual(D(satirlar["A TEDARİK"]), Decimal("1234.56"))
        self.assertEqual(D(satirlar["B TEDARİK"]), Decimal("0.65"))
        self.assertEqual(D(satirlar["TOPLAM"]), Decimal("1235.21"))
        self.assertEqual(ws["B5"].number_format, "#,##0.00")

    def test_yapilan_xlsx(self):
        self.belge(self.a, "ODEME", 10050, date(2026, 1, 10), odeme_sekli="NAKIT", aciklama="Ocak ödemesi")
        v = ol.yapilan_odemeler(date(2026, 1, 1), date(2026, 1, 31))
        ws = self.yukle(ol.yapilan_odemeler_xlsx(v)).active
        self.assertEqual([ws.cell(4, c).value for c in (1, 3, 5)], ["A TEDARİK", "Nakit", "Ocak ödemesi"])
        self.assertEqual(D(ws.cell(4, 6).value), Decimal("100.50"))
        self.assertEqual(ws.cell(4, 2).value.date(), date(2026, 1, 10))
        self.assertEqual(ws["A7"].value, "GENEL TOPLAM")
        self.assertEqual(D(ws["F7"].value), Decimal("100.50"))

    def test_formul_enjeksiyonu_metin_olarak_yazilir(self):
        kotu = Cari.objects.create(unvan='=HYPERLINK("http://kotu.example","tikla")')
        self.belge(kotu, "ALIS_FISI", 100, date(2026, 1, 1), "1")
        self.belge(kotu, "ODEME", 50, date(2026, 1, 2), aciklama="=1+1")
        for baytlar in (ol.odenecekler_xlsx(ol.odenecekler(date(2026, 1, 31))),
                        ol.yapilan_odemeler_xlsx(ol.yapilan_odemeler(date(2026, 1, 1), date(2026, 1, 31)))):
            ws = self.yukle(baytlar).active
            formuller = [h.coordinate for satir in ws.iter_rows() for h in satir if h.data_type == "f"]
            self.assertEqual(formuller, [], "hiçbir hücre formül olmamalı")
        ws = self.yukle(ol.odenecekler_xlsx(ol.odenecekler(date(2026, 1, 31)))).active
        self.assertEqual(ws["A5"].value, '=HYPERLINK("http://kotu.example","tikla")')


class EkranTests(ListeTemel):
    def setUp(self):
        super().setUp()
        self.client.force_login(rol_kullanici("p", "Muhasebe"))
        self.belge(self.a, "ALIS_FISI", 150000, date(2026, 1, 1), "1")
        self.belge(self.a, "ODEME", 40000, date.today(), odeme_sekli="HAVALE", aciklama="Bu ayki")

    def test_giris_gerekli(self):
        self.client.logout()
        r = self.client.get(reverse("odeme_listesi"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])

    def test_odenecekler_ekrani(self):
        r = self.client.get(reverse("odeme_listesi"))
        self.assertContains(r, "A TEDARİK")
        self.assertContains(r, "1.100,00 ₺")             # 1.500 − 400
        self.assertContains(r, "Planlanan ödeme")        # yazdırma sütunu
        self.assertContains(r, "Ödenecekler listesi")

    def test_yapilan_ekrani_ve_filtre(self):
        r = self.client.get(reverse("odeme_listesi"), {"liste": "yapilan", "bas": "2026-01-01",
                                                       "bit": date.today().isoformat()})
        self.assertContains(r, "Bu ayki")
        self.assertContains(r, "400,00 ₺")
        r = self.client.get(reverse("odeme_listesi"), {"liste": "yapilan", "sekil": "NAKIT",
                                                       "bas": "2026-01-01", "bit": date.today().isoformat()})
        self.assertContains(r, "Bu dönemde ödeme yok")

    def test_ters_tarih_yer_degistirir_bozuk_parametre_cokmez(self):
        r = self.client.get(reverse("odeme_listesi"), {"liste": "yapilan", "bas": date.today().isoformat(),
                                                       "bit": "2026-01-01"})
        self.assertContains(r, "yer değiştirdi")
        for kotu in ({"bas": "abc"}, {"liste": "x"}, {"cari": "999999"}, {"cari": "zzz"}, {"sekil": "yok"},
                     {"indir": "pdf"}):
            self.assertEqual(self.client.get(reverse("odeme_listesi"), kotu).status_code, 200, kotu)

    def test_excel_indirme(self):
        r = self.client.get(reverse("odeme_listesi"), {"indir": "xlsx"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        self.assertIn("odenecekler_", r["Content-Disposition"])
        ws = openpyxl.load_workbook(BytesIO(r.content)).active
        self.assertEqual(ws["A5"].value, "A TEDARİK")
        self.assertEqual(D(ws["B5"].value), Decimal("1100"))
        r = self.client.get(reverse("odeme_listesi"), {"liste": "yapilan", "indir": "xlsx", "bas": "2026-01-01",
                                                       "bit": date.today().isoformat()})
        self.assertIn("yapilan_odemeler_", r["Content-Disposition"])
        self.assertNotIn("\n", r["Content-Disposition"])

    def test_cari_filtresi_ekranda(self):
        self.belge(self.b, "ALIS_FISI", 9900, date(2026, 1, 1), "2")
        r = self.client.get(reverse("odeme_listesi"), {"cari": self.b.pk})
        self.assertContains(r, "99,00 ₺")
        self.assertNotContains(r, "1.100,00 ₺")
