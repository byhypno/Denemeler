"""Ofis Kasa raporu: dönem hesabı, kırılımlar, Excel ve PDF."""
import os
import re
import zlib
from datetime import date
from io import BytesIO

import openpyxl
from django.test import TestCase
from django.urls import reverse

from . import kasa_rapor as kr
from .models import Hesap, KasaHareketi, KasaKategori
from .test_yardimci import rol_kullanici

G, C = KasaHareketi.Yon.GIRIS, KasaHareketi.Yon.CIKIS


class Temel(TestCase):
    def setUp(self):
        self.h = Hesap.objects.get(ad="Ofis Kasa")
        self.yemek = KasaKategori.objects.filter(aktif=True).first()

    def m(self, yon, tutar, tarih, **kw):
        return KasaHareketi.objects.create(hesap=self.h, yon=yon, tutar_kurus=tutar, tarih=tarih, **kw)

    def ornek(self):
        self.m(G, 100000, date(2026, 9, 28), aciklama="Eski giriş")                      # devir
        self.m(C, 10000, date(2026, 9, 29), aciklama="Eski çıkış", harcayan="Can")        # devir
        self.m(G, 500000, date(2026, 10, 2), aciklama="PARA GİRİŞİ")
        self.m(C, 62500, date(2026, 10, 2), aciklama="MALZEME & YEMEK <x>", harcayan="Can", makbuz_no="2,1,2,16",
               kategori=self.yemek)
        self.m(C, 40000, date(2026, 10, 3), aciklama="Şantiye yemek", harcayan="Fesih")
        self.m(C, 104000, date(2026, 10, 3), aciklama="Çelik kapı", harcayan="  CAN ", makbuz_no="11")
        self.m(C, 9999, date(2026, 10, 4), aciklama="Çay", harcayan="")
        iptal = self.m(C, 777700, date(2026, 10, 5), aciklama="İPTAL EDİLEN", harcayan="Can")
        KasaHareketi.objects.filter(pk=iptal.pk).update(iptal=True)
        self.m(C, 5555, date(2026, 11, 1), aciklama="Dönem dışı")
        return kr.kasa_raporu(self.h, date(2026, 10, 1), date(2026, 10, 31))


class HesapTests(Temel):
    def test_devir_toplam_kalan(self):
        r = self.ornek()
        self.assertEqual(r["devir"], 90000)
        self.assertEqual(r["giris_toplam"], 500000)
        self.assertEqual(r["cikis_toplam"], 62500 + 40000 + 104000 + 9999)
        self.assertEqual(r["kalan"], r["devir"] + r["giris_toplam"] - r["cikis_toplam"])
        self.assertEqual(r["kalan"], self.h.bakiye_kurus(tarih_kadar=date(2026, 10, 31)))   # kasanın kendi hesabıyla aynı

    def test_iptal_ve_donem_disi_haric(self):
        r = self.ornek()
        acik = [h.aciklama for h in r["cikislar"]]
        self.assertNotIn("İPTAL EDİLEN", acik)
        self.assertNotIn("Dönem dışı", acik)

    def test_harcayan_kirilimi_tekil_ve_belirtilmemis_sonda(self):
        r = self.ornek()
        ad = {k["ad"]: k for k in r["kisiler"]}
        self.assertEqual(ad["Can"]["toplam"], 62500 + 104000)      # 'Can' ile '  CAN ' tek kişi
        self.assertEqual(ad["Can"]["adet"], 2)
        self.assertEqual(r["kisiler"][-1]["ad"], kr.BELIRTILMEMIS)
        self.assertEqual(sum(k["toplam"] for k in r["kisiler"]), r["cikis_toplam"])

    def test_kategori_kirilimi_toplami_tutar(self):
        r = self.ornek()
        self.assertEqual(sum(k["toplam"] for k in r["kategoriler"]), r["cikis_toplam"])
        self.assertIn(kr.KATEGORISIZ, [k["ad"] for k in r["kategoriler"]])

    def test_gunluk_bakiye_zinciri(self):
        r = self.ornek()
        self.assertEqual(r["gunler"][-1]["bakiye"], r["kalan"])
        onceki = r["devir"]
        for g in r["gunler"]:
            self.assertEqual(g["bakiye"], onceki + g["giris"] - g["cikis"])
            onceki = g["bakiye"]

    def test_fissiz_ve_en_buyuk(self):
        r = self.ornek()
        self.assertEqual(r["fissiz_adet"], 2)
        self.assertEqual(r["fissiz_toplam"], 40000 + 9999)
        self.assertEqual(r["en_buyuk"][0].tutar_kurus, 104000)

    def test_bos_donem(self):
        r = kr.kasa_raporu(self.h, date(2030, 1, 1), date(2030, 1, 31))
        self.assertEqual((r["giris_toplam"], r["cikis_toplam"], r["kalan"], r["ortalama_gunluk_cikis"]), (0, 0, 0, 0))
        self.assertTrue(kr.rapor_xlsx(r)); self.assertTrue(kr.rapor_pdf(r))


class DonemTests(Temel):
    BUGUN = date(2026, 3, 15)

    def test_varsayilan_bu_ay(self):
        self.assertEqual(kr.donem_sec(self.h, {}, self.BUGUN)[:2], (date(2026, 3, 1), self.BUGUN))

    def test_onceki_ay_ocakta_yil_doner(self):
        self.assertEqual(kr.donem_sec(self.h, {"donem": "onceki_ay"}, date(2026, 1, 10))[:2], (date(2025, 12, 1), date(2025, 12, 31)))

    def test_son_giristen(self):
        self.m(G, 100, date(2026, 2, 20)); self.m(G, 100, date(2026, 3, 5)); self.m(C, 50, date(2026, 3, 9))
        self.assertEqual(kr.donem_sec(self.h, {"donem": "son_giris"}, self.BUGUN)[:2], (date(2026, 3, 5), self.BUGUN))

    def test_son_giris_yoksa_bu_aya_duser(self):
        self.assertEqual(kr.donem_sec(self.h, {"donem": "son_giris"}, self.BUGUN)[2], "Bu ay")

    def test_ozel_aralik_ve_bozuk_girdi(self):
        self.assertEqual(kr.donem_sec(self.h, {"bas": "2026-01-02", "bit": "2026-01-09"}, self.BUGUN)[:2], (date(2026, 1, 2), date(2026, 1, 9)))
        for kotu in ({"bas": "2026-02-01", "bit": "2026-01-01"}, {"bas": "x", "bit": "y"}, {"bas": "1900-01-01", "bit": "2026-01-01"}):
            self.assertEqual(kr.donem_sec(self.h, kotu, self.BUGUN)[2], "Bu ay")


class ExcelTests(Temel):
    def test_sayfalar_ve_degerler(self):
        r = self.ornek()
        ws = openpyxl.load_workbook(BytesIO(kr.rapor_xlsx(r))).worksheets
        self.assertEqual([s.title for s in ws], ["Kasa defteri", "Özet", "Günlük"])
        d = ws[0]
        degerler = {c.value for satir in d.iter_rows() for c in satir if c.value is not None}
        for beklenen in ("DEVİR", "TOPLAM", "KALAN", "MALZEME & YEMEK <x>", "2,1,2,16"):
            self.assertIn(beklenen, degerler)
        kalan_hucre = next(c for satir in d.iter_rows() for c in satir if c.value == "KALAN")
        self.assertEqual(float(d.cell(row=kalan_hucre.row, column=kalan_hucre.column + 1).value), r["kalan"] / 100)

    def test_formul_enjeksiyonu_olmaz(self):
        self.m(G, 100, date(2026, 10, 2))
        self.m(C, 50, date(2026, 10, 2), aciklama='=HYPERLINK("http://x")', harcayan="=1+1")
        r = kr.kasa_raporu(self.h, date(2026, 10, 1), date(2026, 10, 31))
        wb = openpyxl.load_workbook(BytesIO(kr.rapor_xlsx(r)))
        for ws in wb:
            for satir in ws.iter_rows():
                for c in satir:
                    self.assertNotEqual(c.data_type, "f", f"{ws.title}!{c.coordinate}")


class PdfTests(Temel):
    def pdf_okuyucu(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("pypdf kurulu değil (yalnız test için)")
        return PdfReader

    def test_pdf_uretilir_ve_turkce_gomulur(self):
        r = self.ornek()
        pdf = kr.rapor_pdf(r)
        self.assertTrue(pdf.startswith(b"%PDF"))
        PdfReader = self.pdf_okuyucu()
        metin = "\n".join(s.extract_text() for s in PdfReader(BytesIO(pdf)).pages)
        for beklenen in ("KALAN", "Çelik kapı", "Şantiye yemek", "₺"):
            self.assertIn(beklenen, metin)

    def test_cok_uzun_liste_birden_cok_sayfa(self):
        self.m(G, 10**9, date(2026, 10, 1))
        for i in range(120):
            self.m(C, 100 + i, date(2026, 10, 2), aciklama=f"Kalem {i} " + "uzun açıklama " * 6, harcayan=f"Kişi {i % 7}")
        r = kr.kasa_raporu(self.h, date(2026, 10, 1), date(2026, 10, 31))
        PdfReader = self.pdf_okuyucu()
        pdf = PdfReader(BytesIO(kr.rapor_pdf(r)))
        self.assertGreater(len(pdf.pages), 1)                 # 120 uzun satır tek sayfaya sığmaz; en küçük yazıda çok sayfa

    def test_ornek_dosyalari_yaz(self):
        hedef = os.environ.get("RAPOR_ORNEK_DIZINI")
        if not hedef:
            self.skipTest("RAPOR_ORNEK_DIZINI verilmedi")
        r = self.ornek()
        open(os.path.join(hedef, "ofis_kasa.xlsx"), "wb").write(kr.rapor_xlsx(r))
        open(os.path.join(hedef, "ofis_kasa.pdf"), "wb").write(kr.rapor_pdf(r))


class EkranTests(Temel):
    def giris(self, rol="Muhasebe"):
        self.client.force_login(rol_kullanici("u" + rol[:3], rol))

    def test_anonim_girise_yonlenir(self):
        r = self.client.get(reverse("kasa_rapor"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])

    def test_rolsuz_goremez_diger_roller_gorebilir(self):
        self.client.force_login(rol_kullanici("rolsuz"))
        self.assertNotEqual(self.client.get(reverse("kasa_rapor")).status_code, 200)
        self.client.logout()
        for rol in ("Kasiyer", "Görüntüleyici", "Muhasebe"):
            self.giris(rol)
            self.assertEqual(self.client.get(reverse("kasa_rapor")).status_code, 200, rol)
            self.client.logout()

    def test_onizleme_ve_donem_secenekleri(self):
        self.ornek()
        self.giris()
        r = self.client.get(reverse("kasa_rapor"), {"bas": "2026-10-01", "bit": "2026-10-31"})
        self.assertContains(r, "KALAN")
        self.assertContains(r, "Çelik kapı")
        self.assertContains(r, "MALZEME &amp; YEMEK &lt;x&gt;")       # kaçışlı
        self.assertContains(r, "Belirtilmemiş")
        self.assertContains(r, "fiş/makbuz numarası girilmemiş")
        for ad in ("Bu ay", "Önceki ay", "Son para girişinden bugüne", "Bu yıl"):
            self.assertContains(r, ad)

    def test_dosya_indirme(self):
        self.ornek()
        self.giris()
        q = {"bas": "2026-10-01", "bit": "2026-10-31"}
        x = self.client.get(reverse("kasa_rapor"), {**q, "indir": "xlsx"})
        self.assertIn("spreadsheetml", x["Content-Type"])
        self.assertIn("ofis_kasa_20261001_20261031.xlsx", x["Content-Disposition"])
        openpyxl.load_workbook(BytesIO(x.content))
        p = self.client.get(reverse("kasa_rapor"), {**q, "indir": "pdf"})
        self.assertEqual(p["Content-Type"], "application/pdf")
        self.assertTrue(p.content.startswith(b"%PDF"))

    def test_kasa_sayfasinda_baglanti(self):
        self.giris()
        self.assertContains(self.client.get(reverse("kasa")), reverse("kasa_rapor"))

    def test_bozuk_parametreler_cokmez(self):
        self.giris()
        for q in ({"hesap": "abc"}, {"bas": "zzz", "bit": "2026-01-01"}, {"donem": "<script>"}, {"indir": "exe"}):
            self.assertEqual(self.client.get(reverse("kasa_rapor"), q).status_code, 200, q)


class DenetimDuzeltmeTests(Temel):
    def test_denetim_karakterli_metin_excel_bozmaz(self):
        self.m(G, 100, date(2026, 10, 2))
        self.m(C, 50, date(2026, 10, 2), aciklama="a\x0bb\x01c", harcayan="x\x01y")
        r = kr.kasa_raporu(self.h, date(2026, 10, 1), date(2026, 10, 31))
        self.assertTrue(kr.rapor_xlsx(r))

    def test_formdan_gelen_denetim_karakteri_temizlenir(self):
        self.m(G, 100000, date(2026, 10, 1))
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.post(reverse("kasa"), {"tarih": "2026-10-02", "yon": "CIKIS", "tutar_kurus": "5,00", "kdv_modu": "BILINMIYOR",
                                               "aciklama": "a\x0bb", "harcayan": "x\x01y", "makbuz_no": "1\x02"})
        self.assertEqual(r.status_code, 302)
        h = KasaHareketi.objects.get(yon=C)
        self.assertEqual((h.aciklama, h.harcayan, h.makbuz_no), ("a b", "x y", "1"))

    def test_uc_tarih_reddedilir_ve_yil_secici_cokmez(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        for t in ("0001-01-01", "2206-01-01"):
            r = self.client.post(reverse("kasa"), {"tarih": t, "yon": "GIRIS", "tutar_kurus": "5,00", "kdv_modu": "BILINMIYOR"})
            self.assertEqual(r.status_code, 200, t)
        self.assertFalse(KasaHareketi.objects.exists())
        from . import kasa_servisi as ks
        self.assertEqual(ks.kasa_aylik(self.h, 1)["giris"], [0] * 12)


class GecersizAralikUyariTests(Temel):
    def test_gecersiz_ozel_aralik_uyari_verir(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        r = self.client.get(reverse("kasa_rapor"), {"bas": "2026-05-01", "bit": "2026-01-01"})
        self.assertContains(r, "tarih aralığı geçersiz")
        r = self.client.get(reverse("kasa_rapor"), {"bas": "2026-01-01", "bit": "2026-05-01"})
        self.assertNotContains(r, "tarih aralığı geçersiz")


class PdfTekSayfaTests(Temel):
    def test_dik_a4_ve_makul_kayit_tek_sayfa(self):
        from pypdf import PdfReader
        self.m(G, 10**8, date(2026, 10, 1))
        for i in range(45):
            self.m(C, 1000 + i, date(2026, 10, 2 + i % 20), aciklama=f"ŞANTİYE YEMEK ÜCRETİ {i}", harcayan=f"Kişi {i % 5}", makbuz_no=str(i))
        r = kr.kasa_raporu(self.h, date(2026, 10, 1), date(2026, 10, 31))
        ham = kr.rapor_pdf(r)
        if os.environ.get("RAPOR_ORNEK_DIZINI"):
            open(os.path.join(os.environ["RAPOR_ORNEK_DIZINI"], "tek_sayfa.pdf"), "wb").write(ham)
        pdf = PdfReader(BytesIO(ham))
        self.assertEqual(len(pdf.pages), 1)
        genislik, yukseklik = float(pdf.pages[0].mediabox.width), float(pdf.pages[0].mediabox.height)
        self.assertLess(genislik, yukseklik)                  # dik
        self.assertIn("ŞANTİYE YEMEK ÜCRETİ 44", pdf.pages[0].extract_text())
