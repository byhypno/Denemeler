import os
import tempfile
import unittest
from datetime import date

import openpyxl
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .excel_aktar import excel_beklenen_bakiyeler, ice_aktar, kurus
from .fields import kurus_bicimle, tl_ayristir
from .kdv import KdvModu, kdv_hesapla
from datetime import timedelta

from .models import Belge, BelgeKalem, Cari, EkstreMutabakat, EkstreSatiri, Hesap, KasaHareketi
from . import services
from .services import bakiye_kurus, ekstre


class ParaAlaniTests(TestCase):
    def test_bicimle(self):
        self.assertEqual(kurus_bicimle(123450), "1.234,50")
        self.assertEqual(kurus_bicimle(5), "0,05")
        self.assertEqual(kurus_bicimle(-100000), "-1.000,00")
        self.assertEqual(kurus_bicimle(100000000), "1.000.000,00")

    def test_ayristir_gecerli(self):
        self.assertEqual(tl_ayristir("1.234,50"), 123450)
        self.assertEqual(tl_ayristir("1234,5"), 123450)
        self.assertEqual(tl_ayristir("1234"), 123400)
        self.assertEqual(tl_ayristir("₺ 7.646,65"), 764665)
        self.assertEqual(tl_ayristir("-12,30"), -1230)

    def test_ayristir_belirsiz_reddedilir(self):
        # "1234.50" yanlışlıkla 123.450 TL olmasın diye reddedilir
        for kotu in ["1234.50", "1,234.50", "12,345", "abc", "1.23", ""]:
            with self.assertRaises(ValueError, msg=kotu):
                tl_ayristir(kotu)

    def test_gidis_donus(self):
        for k in (0, 1, 99, 100, 123456789, 64718_10):
            self.assertEqual(tl_ayristir(kurus_bicimle(k)), k)

    def test_excel_float_artigi_kuruse_dogru_donusur(self):
        # 64718.1099999999 Excel'in kayan nokta artığıdır; gerçek değer 64.718,11 ₺
        self.assertEqual(kurus(64718.1099999999), 6471811)
        self.assertEqual(kurus(2919.17), 291917)


class KdvTests(TestCase):
    def test_haric(self):
        h = kdv_hesapla(100000, 20, KdvModu.HARIC)
        self.assertEqual((h["matrah_kurus"], h["kdv_kurus"], h["odenecek_kurus"]), (100000, 20000, 120000))

    def test_dahil(self):
        h = kdv_hesapla(120000, 20, KdvModu.DAHIL)
        self.assertEqual((h["matrah_kurus"], h["kdv_kurus"], h["odenecek_kurus"]), (100000, 20000, 120000))

    def test_dahil_yuvarlama_toplami_bozmaz(self):
        h = kdv_hesapla(9999, 20, KdvModu.DAHIL)
        self.assertEqual(h["matrah_kurus"] + h["kdv_kurus"], 9999)

    def test_tevkifat(self):
        # matrah 1000 TL, KDV %20 = 200 TL, tevkifat KDV'nin %50'si = 100 TL -> ödenecek 1100 TL
        h = kdv_hesapla(100000, 20, KdvModu.HARIC, tevkifat_orani=50)
        self.assertEqual(h["tevkifat_kurus"], 10000)
        self.assertEqual(h["odenecek_kurus"], 110000)

    def test_tevkifat_dahilde_hata(self):
        with self.assertRaises(ValueError):
            kdv_hesapla(100000, 20, KdvModu.DAHIL, tevkifat_orani=50)

    def test_yarim_yukari_yuvarlama(self):
        # 2,5 kuruş KDV -> 3 kuruş (yarım yukarı)
        self.assertEqual(kdv_hesapla(25, 10, KdvModu.HARIC)["kdv_kurus"], 3)


class BakiyeTests(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="TEST A.Ş.")

    def belge(self, tur, tutar, gun=1, **kw):
        return Belge.objects.create(cari=self.cari, tur=tur, tarih=date(2026, 1, gun),
                                    tutar_kurus=tutar, **kw)

    def test_bakiye_turlere_gore(self):
        self.belge(Belge.Tur.ACILIS, 100000)
        self.belge(Belge.Tur.ALIS_FISI, 50000, evrak_no="001", gun=2)
        self.belge(Belge.Tur.ODEME, 30000, gun=3)
        self.belge(Belge.Tur.IADE, 10000, evrak_no="002", gun=4)
        self.belge(Belge.Tur.DUZELTME_ARTI, 500, gun=5)
        self.belge(Belge.Tur.DUZELTME_EKSI, 200, gun=6)
        self.assertEqual(bakiye_kurus(self.cari), 100000 + 50000 - 30000 - 10000 + 500 - 200)

    def test_iptal_sayilmaz(self):
        self.belge(Belge.Tur.ALIS_FISI, 50000, evrak_no="001")
        b = self.belge(Belge.Tur.ALIS_FISI, 70000, evrak_no="002")
        b.iptal, b.iptal_nedeni = True, "yanlış giriş"
        b.save()
        self.assertEqual(bakiye_kurus(self.cari), 50000)

    def test_tarihe_kadar(self):
        self.belge(Belge.Tur.ALIS_FISI, 100, evrak_no="1", gun=1)
        self.belge(Belge.Tur.ALIS_FISI, 200, evrak_no="2", gun=10)
        self.assertEqual(bakiye_kurus(self.cari, tarih_kadar=date(2026, 1, 5)), 100)

    def test_ekstre_yuruyen_bakiye(self):
        self.belge(Belge.Tur.ACILIS, 1000, gun=1)
        self.belge(Belge.Tur.ODEME, 400, gun=5)
        self.belge(Belge.Tur.ALIS_FISI, 250, evrak_no="9", gun=7)
        onceki, satirlar = ekstre(self.cari, baslangic=date(2026, 1, 5))
        self.assertEqual(onceki, 1000)
        self.assertEqual([b for _, b in satirlar], [600, 850])

    def test_tutar_sifir_veya_negatif_veritabaninda_reddedilir(self):
        for tutar in (0, -5):
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.belge(Belge.Tur.ALIS_FISI, tutar, evrak_no=f"x{tutar}")

    def test_ayni_evrak_no_tekrarlanamaz_ama_iptalden_sonra_girilebilir(self):
        b = self.belge(Belge.Tur.ALIS_FISI, 100, evrak_no="007")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.belge(Belge.Tur.ALIS_FISI, 200, evrak_no="007")
        b.iptal, b.iptal_nedeni = True, "hatalı"
        b.save()
        self.belge(Belge.Tur.ALIS_FISI, 200, evrak_no="007")  # artık serbest

    def test_belge_kdv_haric_kayitta_cozulur(self):
        b = self.belge(Belge.Tur.ALIS_FATURASI, 100000, evrak_no="F1",
                       kdv_modu=KdvModu.HARIC, kdv_orani=20, tevkifat_orani=50)
        b.refresh_from_db()
        self.assertEqual((b.matrah_kurus, b.kdv_kurus, b.tevkifat_kurus, b.tutar_kurus),
                         (100000, 20000, 10000, 110000))
        self.assertEqual(bakiye_kurus(self.cari), 110000)

    def test_kdv_yeniden_kayitta_cift_hesaplanmaz(self):
        b = self.belge(Belge.Tur.ALIS_FATURASI, 100000, evrak_no="F2",
                       kdv_modu=KdvModu.HARIC, kdv_orani=20)
        b.aciklama = "değişti"
        b.save()
        b.refresh_from_db()
        self.assertEqual(b.tutar_kurus, 120000)

    def test_kdv_tutarsizligi_clean_yakalar(self):
        b = self.belge(Belge.Tur.ALIS_FATURASI, 100000, evrak_no="F3",
                       kdv_modu=KdvModu.HARIC, kdv_orani=20)
        b.tutar_kurus = 999
        with self.assertRaises(ValidationError):
            b.full_clean()

    def test_kdv_modu_oransiz_hata(self):
        b = Belge(cari=self.cari, tur=Belge.Tur.ALIS_FISI, tarih=date(2026, 1, 1),
                  tutar_kurus=100, kdv_modu=KdvModu.HARIC)
        with self.assertRaises(ValidationError):
            b.full_clean()


class KasaTests(TestCase):
    def test_ofis_kasa_hazir_ve_tl(self):
        self.assertTrue(Hesap.objects.filter(ad="Ofis Kasa", tur=Hesap.Tur.KASA).exists())

    def test_bakiye_ve_eksi_engeli(self):
        kasa = Hesap.objects.get(ad="Ofis Kasa")
        KasaHareketi.objects.create(hesap=kasa, tarih=date(2026, 1, 1), yon="GIRIS", tutar_kurus=100000)
        KasaHareketi.objects.create(hesap=kasa, tarih=date(2026, 1, 2), yon="CIKIS", tutar_kurus=30000)
        self.assertEqual(kasa.bakiye_kurus(), 70000)
        fazla = KasaHareketi(hesap=kasa, tarih=date(2026, 1, 3), yon="CIKIS", tutar_kurus=70001)
        with self.assertRaises(ValidationError):
            fazla.full_clean()
        tam = KasaHareketi(hesap=kasa, tarih=date(2026, 1, 3), yon="CIKIS", tutar_kurus=70000)
        tam.full_clean()  # sıfıra inmek serbest

    def test_eksiye_dusebilir_ayari(self):
        kasa = Hesap.objects.get(ad="Ofis Kasa")
        kasa.eksiye_dusebilir = True
        kasa.save()
        KasaHareketi(hesap=kasa, tarih=date(2026, 1, 3), yon="CIKIS", tutar_kurus=500).full_clean()

    def test_iptal_bakiyeye_dahil_degil(self):
        kasa = Hesap.objects.get(ad="Ofis Kasa")
        KasaHareketi.objects.create(hesap=kasa, tarih=date(2026, 1, 1), yon="GIRIS", tutar_kurus=1000)
        KasaHareketi.objects.create(hesap=kasa, tarih=date(2026, 1, 1), yon="GIRIS", tutar_kurus=9999,
                                    iptal=True, iptal_nedeni="hatalı")
        self.assertEqual(kasa.bakiye_kurus(), 1000)

    def test_kasa_ve_cari_odemesi_birbirini_degistirmez(self):
        cari = Cari.objects.create(unvan="X")
        kasa = Hesap.objects.get(ad="Ofis Kasa")
        odeme = Belge.objects.create(cari=cari, tur=Belge.Tur.ODEME, tarih=date(2026, 1, 1),
                                     tutar_kurus=5000)
        KasaHareketi.objects.create(hesap=kasa, tarih=date(2026, 1, 1), yon="GIRIS", tutar_kurus=9000)
        KasaHareketi.objects.create(hesap=kasa, tarih=date(2026, 1, 1), yon="CIKIS", tutar_kurus=5000,
                                    cari=cari, ilgili_odeme=odeme)
        self.assertEqual(bakiye_kurus(cari), -5000)      # sadece cari ödemesi
        self.assertEqual(kasa.bakiye_kurus(), 4000)      # sadece kasa hareketi
        self.assertEqual(Belge.objects.count(), 1)       # kasa girişi cari belge üretmedi


def _ornek_excel(yol, ikinci_odeme_fazla=False, mutabakat=False):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tedarikçiler"
    ws.append(["Tedarikçi Kartları"])
    ws.append([])
    ws.append(["Tedarikçi Adı", "Kısa Kod", "Cari Kodu", "Vergi", "Tel", "E-posta", "Yetkili",
               "Vade", "Alış", "Ödeme", "Güncel Borcumuz", "Not"])
    ws.append(["TEST HIRDAVAT", "TEST", "120-1", None, None, None, None, 30, None, None, 11850.55, None])
    h = wb.create_sheet("Hareketler")
    h.append(["Cari Hareketler"])
    h.append([]); h.append([])
    h.append(["Tarih", "Evrak Türü", "Tedarikçi", "Evrak / Fiş No", "Tedarikçi Evrak No", "Açıklama",
              "Ödeme Şekli", "Elle Tutar", "Etki", "Borç Artışı", "Borç Azalışı", "Bakiye", "Durum", "Not"])
    h.append([date(2026, 1, 1), "Açılış / Devir", "TEST HIRDAVAT", None, "0000001", "devir", None,
              10000.1, "Artırır", 10000.1, None, None, None, None])
    h.append([date(2026, 1, 2), "Alış Fişi", "TEST HIRDAVAT", "001", "0000002", "alım", None,
              None, "Artırır", 3000.45, None, None, None, None])
    h.append([date(2026, 1, 3), "İade", "TEST HIRDAVAT", "002", None, "iade", None,
              None, "Azaltır", None, 500, None, None, None])
    h.append([date(2026, 1, 4), "Ödeme", "TEST HIRDAVAT", None, None, "ödeme", "Havale/EFT",
              650.0 + (1 if ikinci_odeme_fazla else 0), "Azaltır", None, 650.0, None, None, None])
    h.append([None] * 14)
    k = wb.create_sheet("Fiş Kalemleri")
    k.append(["Fiş / Fatura Kalemleri"]); k.append([])
    k.append(["Fiş No", "Tarih", "Tedarikçi", "Stok", "Açıklama", "Miktar", "Birim", "Birim Fiyat", "Tutar"])
    k.append(["001", date(2026, 1, 2), "TEST HIRDAVAT", "A-1", "Vida", 10, "ADET", 150.045, 1500.45])
    k.append(["001", date(2026, 1, 2), "TEST HIRDAVAT", "A-2", "Somun", 5, "ADET", 300, 1500])
    k.append(["002", date(2026, 1, 3), "TEST HIRDAVAT", "A-3", "Iade vida", 1, "ADET", 500, 500])
    if mutabakat:
        e = wb.create_sheet("Ekstre Mutabakatı")
        e.append(["Ekstre Mutabakatı — TEST HIRDAVAT"])
        e.append(["Tedarikçinin 05.02.2026 tarihli cari ekstresi ile bizim kayıtlarımızın karşılaştırması."])
        e.append([])
        e.append(["Fiş No", "Tarih", "Tür", "Bizim Kayıt", "Ekstre Evrak No", "Ekstre Tutarı", "Fark", "Durum / Açıklama"])
        e.append(["001", date(2026, 1, 2), "Alış", 3000.45, "0000002", 3000.0, 0.45, "FARK — 0,45 düşük"])
        e.append(["002", date(2026, 1, 3), "İade", 500, "0000009", 500, 0, "✓ Uyumlu"])
        e.append([])
        e.append(["Özet"])
        e.append(["Kalem", None, None, "Bizim Kayıt", None, "Ekstre", "Fark"])
        e.append(["Bakiye (borcumuz)", None, None, 11850.55, None, 11850.10, 0.45])
    wb.save(yol)


class ExcelAktarTests(TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.addCleanup(self.dizin.cleanup)
        self.yol = os.path.join(self.dizin.name, "ornek.xlsx")
        _ornek_excel(self.yol)

    def test_aktarim_ve_bakiye(self):
        ozet = ice_aktar(self.yol)
        self.assertEqual((ozet["cari"], ozet["belge"], ozet["kalem"]), (1, 4, 3))
        self.assertEqual(ozet["hatalar"], [])
        self.assertEqual(ozet["uyarilar"], [])
        cari = Cari.objects.get(unvan="TEST HIRDAVAT")
        # 10000,10 + 3000,45 - 500 - 650 = 11850,55
        self.assertEqual(cari.bakiye_kurus(), 1185055)
        self.assertEqual(excel_beklenen_bakiyeler(self.yol), {"TEST HIRDAVAT": 1185055})
        self.assertEqual(cari.vade_gun, 30)

    def test_kalemler_dogru_baglanir(self):
        ice_aktar(self.yol)
        fis = Belge.objects.get(evrak_no="001")
        self.assertEqual(fis.kalemler.count(), 2)
        self.assertEqual(sum(x.tutar_kurus for x in fis.kalemler.all()), fis.tutar_kurus)
        self.assertEqual(Belge.objects.get(tur=Belge.Tur.ODEME).odeme_sekli, Belge.OdemeSekli.HAVALE)

    def test_ikinci_kez_aktarmak_sifirla_ister(self):
        ice_aktar(self.yol)
        with self.assertRaises(RuntimeError):
            ice_aktar(self.yol)
        ozet = ice_aktar(self.yol, sifirla=True)
        self.assertEqual(ozet["belge"], 4)
        self.assertEqual(Cari.objects.count(), 1)

    def test_etki_uyusmazligi_hata_verir_ve_geri_alinir(self):
        _ornek_excel(self.yol)
        wb = openpyxl.load_workbook(self.yol)
        wb["Hareketler"]["I6"] = "Azaltır"  # Alış fişi için yanlış etki
        wb.save(self.yol)
        ozet = ice_aktar(self.yol)
        self.assertTrue(any("etki uyuşmuyor" in h for h in ozet["hatalar"]))
        self.assertEqual(Belge.objects.count(), 0)  # rollback

    def test_kalem_toplami_farkli_ise_uyari(self):
        wb = openpyxl.load_workbook(self.yol)
        wb["Fiş Kalemleri"]["I5"] = 1400  # 001 kalem toplamı belge tutarından farklı
        wb.save(self.yol)
        ozet = ice_aktar(self.yol)
        self.assertTrue(any("kalem toplamı farklı" in u for u in ozet["uyarilar"]))


class AdminDuzeniTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("yonetici", password="Guclu-Parola-9")
        self.client.force_login(self.user)
        self.cari = Cari.objects.create(unvan="ADMIN TEST")

    def test_sayfalar_aciliyor(self):
        for ad in ("cari", "belge", "hesap", "kasahareketi", "kasakategori"):
            for gorunum in ("changelist", "add"):
                r = self.client.get(reverse(f"admin:defter_{ad}_{gorunum}"))
                self.assertEqual(r.status_code, 200, f"{ad} {gorunum}")

    def _belge_post(self, tutar):
        return self.client.post(reverse("admin:defter_belge_add"), {
            "cari": self.cari.pk, "tur": "ALIS_FISI", "tarih": "05.01.2026", "evrak_no": "A1",
            "harici_evrak_no": "", "aciklama": "", "odeme_sekli": "", "kaynak_notu": "",
            "tutar_kurus": tutar, "kdv_modu": "BILINMIYOR",
            "kalemler-TOTAL_FORMS": "0", "kalemler-INITIAL_FORMS": "0",
            "kalemler-MIN_NUM_FORMS": "0", "kalemler-MAX_NUM_FORMS": "1000",
        })

    def test_turk_biciminde_tutar_kaydedilir(self):
        r = self._belge_post("1.234,50")
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["adminform"].form.errors)
        self.assertEqual(Belge.objects.get(evrak_no="A1").tutar_kurus, 123450)

    def test_belirsiz_tutar_reddedilir(self):
        r = self._belge_post("1234.50")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Belge.objects.count(), 0)
        self.assertContains(r, "1.234,50 biçiminde")

    def test_silme_yetkisi_yok(self):
        b = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 1),
                                 tutar_kurus=100, evrak_no="S1")
        r = self.client.post(reverse("admin:defter_belge_delete", args=[b.pk]), {"post": "yes"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Belge.objects.filter(pk=b.pk).exists())


class ExcelMutabakatAktarTests(TestCase):
    def test_mutabakat_sayfasi_aktarilir(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "m.xlsx")
            _ornek_excel(yol, mutabakat=True)
            ozet = ice_aktar(yol)
        self.assertEqual(ozet["hatalar"], [])
        self.assertEqual(ozet["mutabakat_satiri"], 2)
        m = EkstreMutabakat.objects.get()
        self.assertEqual(m.ekstre_tarihi, date(2026, 2, 5))
        self.assertEqual(m.ekstre_bakiye_kurus, 1185010)
        oz = services.mutabakat_ozeti(m)
        self.assertEqual(oz["bizim_bakiye_kurus"], 1185055)
        self.assertEqual(oz["fark_kurus"], 45)
        self.assertEqual(oz["aciklanan_kurus"], 45)
        self.assertEqual(oz["aciklanamayan_kurus"], 0)
        self.assertEqual(len(oz["farkli_satirlar"]), 1)

    def test_mutabakat_sayfasi_yoksa_sorun_degil(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "m.xlsx")
            _ornek_excel(yol)
            ozet = ice_aktar(yol)
        self.assertEqual(ozet["mutabakat_satiri"], 0)
        self.assertFalse(EkstreMutabakat.objects.exists())


class MutabakatHesapTests(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="M")
        self.alis = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 5),
                                         tutar_kurus=100000, evrak_no="1")
        self.iade = Belge.objects.create(cari=self.cari, tur="IADE", tarih=date(2026, 1, 6),
                                         tutar_kurus=30000, evrak_no="2")

    def mut(self, ekstre_bakiye):
        return EkstreMutabakat.objects.create(cari=self.cari, ekstre_tarihi=date(2026, 1, 31),
                                              ekstre_bakiye_kurus=ekstre_bakiye)

    def test_aciklanamayan_fark(self):
        m = self.mut(ekstre_bakiye=65000)   # bizim 70.000; ekstre 65.000 -> fark 5.000
        EkstreSatiri.objects.create(mutabakat=m, belge=self.alis, ekstre_tutar_kurus=97000)  # 3.000 açıklıyor
        oz = services.mutabakat_ozeti(m)
        self.assertEqual(oz["fark_kurus"], 5000)
        self.assertEqual(oz["aciklanan_kurus"], 3000)
        self.assertEqual(oz["aciklanamayan_kurus"], 2000)

    def test_iade_farki_bakiyeye_ters_yansir(self):
        m = self.mut(ekstre_bakiye=70000 + 1000)  # ekstrede iade 1.000 eksik -> ekstre bakiyesi 1.000 fazla
        EkstreSatiri.objects.create(mutabakat=m, belge=self.iade, ekstre_tutar_kurus=29000)
        oz = services.mutabakat_ozeti(m)
        self.assertEqual(oz["fark_kurus"], -1000)
        self.assertEqual(oz["aciklanan_kurus"], -1000)
        self.assertEqual(oz["aciklanamayan_kurus"], 0)

    def test_satir_durumlari(self):
        m = self.mut(0)
        D = EkstreSatiri.Durum
        self.assertEqual(EkstreSatiri(mutabakat=m, belge=self.alis, ekstre_tutar_kurus=100000).durum, D.UYUMLU)
        self.assertEqual(EkstreSatiri(mutabakat=m, belge=self.alis, ekstre_tutar_kurus=1).durum, D.FARKLI)
        self.assertEqual(EkstreSatiri(mutabakat=m, belge=self.alis).durum, D.EKSTREDE_YOK)
        self.assertEqual(EkstreSatiri(mutabakat=m, ekstre_tutar_kurus=500).durum, D.BIZDE_YOK)

    def test_ayni_cari_ayni_tarih_ikinci_mutabakat_olmaz(self):
        self.mut(0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.mut(1)


class YaslandirmaTests(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="Y")

    def belge(self, tur, tutar, tarih, no=""):
        return Belge.objects.create(cari=self.cari, tur=tur, tutar_kurus=tutar, tarih=tarih, evrak_no=no)

    def test_fifo_odeme_en_eski_borca_mahsup_edilir(self):
        self.belge("ALIS_FISI", 10000, date(2026, 1, 1), "A")
        self.belge("ALIS_FISI", 20000, date(2026, 1, 10), "B")
        self.belge("ODEME", 15000, date(2026, 1, 20))
        kalemler, avans = services.acik_kalemler(date(2026, 1, 31))
        self.assertEqual(avans, 0)
        self.assertEqual([(k["belge"].evrak_no, k["kalan_kurus"]) for k in kalemler], [("B", 15000)])
        self.assertEqual(sum(k["kalan_kurus"] for k in kalemler), bakiye_kurus(self.cari))

    def test_avans_sonraki_alistan_dusulur(self):
        self.belge("ODEME", 50000, date(2026, 1, 1))
        self.belge("ALIS_FISI", 20000, date(2026, 1, 5), "A")
        self.belge("ALIS_FISI", 40000, date(2026, 1, 6), "B")
        kalemler, avans = services.acik_kalemler(date(2026, 1, 31))
        self.assertEqual(avans, 0)
        self.assertEqual([(k["belge"].evrak_no, k["kalan_kurus"]) for k in kalemler], [("B", 10000)])
        self.assertEqual(sum(k["kalan_kurus"] for k in kalemler), bakiye_kurus(self.cari))

    def test_fazla_odeme_avans_olarak_kalir(self):
        self.belge("ALIS_FISI", 10000, date(2026, 1, 1), "A")
        self.belge("ODEME", 25000, date(2026, 1, 2))
        kalemler, avans = services.acik_kalemler(date(2026, 1, 31))
        self.assertEqual((kalemler, avans), ([], 15000))

    def test_iptal_sayilmaz(self):
        b = self.belge("ALIS_FISI", 10000, date(2026, 1, 1), "A")
        b.iptal, b.iptal_nedeni = True, "x"
        b.save()
        self.assertEqual(services.acik_kalemler(date(2026, 1, 31)), ([], 0))

    def test_kova_sinirlari(self):
        t = date(2026, 1, 1)
        self.belge("ALIS_FISI", 100, t, "A")
        beklenen = {30: 0, 31: 1, 60: 1, 61: 2, 90: 2, 91: 3}
        for gun, kova in beklenen.items():
            kalemler, _ = services.acik_kalemler(t + timedelta(days=gun))
            self.assertEqual(kalemler[0]["kova"], kova, f"{gun} gün")

    def test_yaslandirma_toplami_bakiyeye_esit(self):
        self.belge("ALIS_FISI", 10000, date(2026, 1, 1), "A")
        self.belge("ALIS_FISI", 20000, date(2026, 2, 1), "B")
        self.belge("ODEME", 5000, date(2026, 2, 2))
        y = services.yaslandirma(date(2026, 3, 1))
        self.assertEqual(y["toplam_acik_kurus"], bakiye_kurus(self.cari))
        self.assertFalse(y["vade_tanimli"])

    def test_vade_gecmis_yalniz_vadesi_tanimli_cariler_icin(self):
        self.belge("ALIS_FISI", 10000, date(2026, 1, 1), "A")
        y = services.yaslandirma(date(2026, 3, 1))
        self.assertEqual(y["vadesi_gecmis_kurus"], 0)
        self.cari.vade_gun = 30
        self.cari.save()
        y = services.yaslandirma(date(2026, 3, 1))
        self.assertTrue(y["vade_tanimli"])
        self.assertEqual(y["vadesi_gecmis_kurus"], 10000)
        y = services.yaslandirma(date(2026, 1, 20))   # vade 31 Ocak, henüz gelmedi
        self.assertEqual(y["vadesi_gecmis_kurus"], 0)


class AylikOzetVeKontrolTests(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="A")

    def belge(self, tur, tutar, tarih, no="", **kw):
        return Belge.objects.create(cari=self.cari, tur=tur, tutar_kurus=tutar, tarih=tarih, evrak_no=no, **kw)

    def test_aylik_ozet_ve_ay_sonu_bakiye(self):
        self.belge("ACILIS", 100000, date(2025, 12, 31))
        self.belge("ALIS_FISI", 50000, date(2026, 1, 10), "1")
        self.belge("ODEME", 30000, date(2026, 2, 3))
        self.belge("IADE", 5000, date(2026, 2, 4), "2")
        a = services.aylik_ozet(2026, bugun=date(2026, 2, 15))
        self.assertEqual((a["alis"][0], a["odeme"][1], a["iade"][1]), (50000, 30000, 5000))
        self.assertEqual(a["onceki_bakiye"], 100000)
        self.assertEqual(a["ay_sonu"][0], 150000)
        self.assertEqual(a["ay_sonu"][1], 115000)
        self.assertIsNone(a["ay_sonu"][2])        # gelecek ay boş bırakılır

    def test_aylik_ozet_gecmis_yilda_12_ay_dolu(self):
        self.belge("ALIS_FISI", 100, date(2025, 3, 1), "1")
        a = services.aylik_ozet(2025, bugun=date(2026, 6, 1))
        self.assertTrue(all(x is not None for x in a["ay_sonu"]))

    def test_kontrol_eksi_bakiye_ayi(self):
        self.belge("ALIS_FISI", 10000, date(2026, 1, 5), "1")
        self.belge("ODEME", 25000, date(2026, 2, 5))
        k = services.kontrol_listesi(date(2026, 3, 10))
        self.assertEqual([(e["ay"], e["bakiye_kurus"]) for e in k["eksi_bakiye"]], [(2, -15000), (3, -15000)])

    def test_kontrol_tekrar_eden_harici_evrak_no(self):
        self.belge("ALIS_FISI", 100, date(2026, 1, 1), "1", harici_evrak_no="X1")
        self.belge("ALIS_FISI", 100, date(2026, 1, 2), "2", harici_evrak_no="X1")
        self.belge("ALIS_FISI", 100, date(2026, 1, 3), "3", harici_evrak_no="Y")
        k = services.kontrol_listesi(date(2026, 1, 31))
        self.assertEqual(len(k["tekrar_evrak_no"]), 1)
        self.assertEqual(len(k["tekrar_evrak_no"][0]), 2)

    def test_temiz_veride_kontrol_adedi_sifir(self):
        self.belge("ALIS_FISI", 100, date(2026, 1, 1), "1")
        self.assertEqual(services.kontrol_listesi(date(2026, 1, 31))["adet"], 0)

    def test_cari_bakiyeleri_siralama(self):
        b = Cari.objects.create(unvan="B")
        Belge.objects.create(cari=b, tur="ALIS_FISI", tutar_kurus=900, tarih=date(2026, 1, 1))
        self.belge("ALIS_FISI", 100, date(2026, 1, 1), "1")
        self.assertEqual([(c.unvan, t) for c, t in services.cari_bakiyeleri()], [("B", 900), ("A", 100)])

    def test_en_cok_alinan_kalemler_iadeyi_saymaz(self):
        alis = self.belge("ALIS_FISI", 300, date(2026, 1, 1), "1")
        iade = self.belge("IADE", 100, date(2026, 1, 2), "2")
        BelgeKalem.objects.create(belge=alis, aciklama="Vida", tutar_kurus=300)
        BelgeKalem.objects.create(belge=iade, aciklama="Vida", tutar_kurus=100)
        self.assertEqual(services.en_cok_alinan_kalemler(2026), [("Vida", 300)])


class EkranTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("p", password="x", is_staff=True)
        self.cari = Cari.objects.create(unvan="EKRAN TEDARİKÇİ")

    def giris(self):
        self.client.force_login(self.user)

    def test_giris_gerekli(self):
        for ad, args in (("dashboard", []), ("mutabakat_liste", []), ("cari_ekstre", [self.cari.pk])):
            r = self.client.get(reverse(ad, args=args))
            self.assertEqual(r.status_code, 302, ad)
            self.assertIn("/admin/login/", r["Location"])

    def test_staff_olmayan_kullanici_giremez(self):
        sade = get_user_model().objects.create_user("s", password="x", is_staff=False)
        self.client.force_login(sade)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_bos_veritabaninda_bos_durum(self):
        self.giris()
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Henüz kayıt yok")

    def test_dashboard_degerleri(self):
        self.giris()
        Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 5),
                             tutar_kurus=123450, evrak_no="1")
        r = self.client.get(reverse("dashboard"), {"yil": "2026"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "1.234,50 ₺")
        self.assertContains(r, "chart.umd.js")
        r = self.client.get(reverse("dashboard"), {"yil": "abc", "cari": str(self.cari.pk)})
        self.assertEqual(r.status_code, 200)     # geçersiz yıl çökmez
        r = self.client.get(reverse("dashboard"), {"cari": "999999"})
        self.assertEqual(r.status_code, 200)     # olmayan cari çökmez

    def test_dashboard_mutabakat_farkini_gosterir(self):
        self.giris()
        b = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 5),
                                 tutar_kurus=100000, evrak_no="1")
        m = EkstreMutabakat.objects.create(cari=self.cari, ekstre_tarihi=date(2026, 1, 31),
                                           ekstre_bakiye_kurus=90000)
        EkstreSatiri.objects.create(mutabakat=m, belge=b, ekstre_tutar_kurus=90000, aciklama="eksik fatura")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "100,00 ₺")
        r = self.client.get(reverse("mutabakat_detay", args=[m.pk]))
        self.assertContains(r, "eksik fatura")
        self.assertContains(r, "Tüm fark açıklandı")
        self.assertEqual(self.client.get(reverse("mutabakat_liste")).status_code, 200)

    def test_ekstre_donem_basi_ve_iptal(self):
        self.giris()
        Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 5), tutar_kurus=100000, evrak_no="1")
        Belge.objects.create(cari=self.cari, tur="ODEME", tarih=date(2026, 2, 5), tutar_kurus=40000)
        Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 2, 6), tutar_kurus=999999,
                             evrak_no="IPTAL", iptal=True, iptal_nedeni="x")
        r = self.client.get(reverse("cari_ekstre", args=[self.cari.pk]), {"bas": "01.02.2026"})
        self.assertContains(r, "1.000,00 ₺")      # dönem başı
        self.assertContains(r, "600,00 ₺")        # kapanış
        self.assertNotContains(r, "IPTAL")
        r = self.client.get(reverse("cari_ekstre", args=[self.cari.pk]), {"bas": "abc"})
        self.assertContains(r, "gg.aa.yyyy")


@unittest.skipUnless(os.environ.get("CARI_EXCEL_YOL"),
                     "Gerçek Excel ile kabul testi: CARI_EXCEL_YOL ortam değişkenini verin")
class GercekExcelKabulTesti(TestCase):
    """Kabul testi 1: içe aktarılan veriden hesaplanan bakiye, Excel'in bakiyesiyle KURUŞU KURUŞUNA eşleşmeli.
    Beklenen değer repoda tutulmaz; çalışma anında Excel'den okunur."""

    def test_bakiyeler_excelle_birebir(self):
        yol = os.environ["CARI_EXCEL_YOL"]
        ozet = ice_aktar(yol)
        self.assertEqual(ozet["hatalar"], [])
        beklenen = excel_beklenen_bakiyeler(yol)
        self.assertTrue(beklenen)
        for unvan, kurus_beklenen in beklenen.items():
            self.assertEqual(Cari.objects.get(unvan=unvan).bakiye_kurus(), kurus_beklenen, unvan)
