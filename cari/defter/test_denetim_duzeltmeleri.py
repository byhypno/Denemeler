"""Bağımsız kod denetiminde bulunan hataların düzeltmeleri (her biri önce yeniden üretildi)."""
import sqlite3
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import gider_servisi as gs
from . import malzeme_servisi as ms
from . import metin
from . import yedek as yd
from .fields import MAKS_KURUS, tl_ayristir
from .models import Belge, BelgeKalem, Cari, GiderKategori, Hesap, KasaHareketi, Malzeme, MalzemeKategori
from .test_yardimci import rol_kullanici
from .test_yedek import PNG, YedekTemel


class Temel(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="Denetim Tedarik")
        self.url = reverse("belge_yeni", args=[self.cari.pk])
        self.client.force_login(rol_kullanici("m", "Muhasebe"))

    def post(self, **kw):
        d = {"tur": "ALIS_FISI", "tarih": "2026-03-05", "tutar_kurus": "100,00", "kdv_modu": "BILINMIYOR"}
        d.update(kw)
        return self.client.post(self.url, d)


class SifirFiyatTests(Temel):
    def kalemli(self, fiyat, tutar="", **kw):
        return self.post(tutar_kurus="", kalem_sayisi="1", kalem_aciklama_0="Vida", kalem_miktar_0="1", kalem_fiyat_0=fiyat,
                         kalem_tutar_0=tutar, **kw)

    def test_formda_sifir_birim_fiyat_reddedilir(self):
        r = self.kalemli("0,00", tutar="50,00")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "birim fiyat sıfırdan büyük olmalı")
        self.assertEqual(Belge.objects.count(), 0)

    def test_eski_sifir_fiyatli_kalem_sayfalari_bozmaz(self):
        """DB'de birim_fiyat=0 olan kalem (yönetim paneli/eski veri) fiyat geçmişini ve sayfaları 500 yapmamalı."""
        for no, gun in (("1", 1), ("2", 2)):
            b = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 3, gun), tutar_kurus=5000, evrak_no=no)
            BelgeKalem.objects.create(belge=b, aciklama="Sıfırlı", miktar=1, birim_fiyat=Decimal("0"), tutar_kurus=5000)
        m = Malzeme.objects.get(ad="Sıfırlı")
        self.assertEqual(ms.birim_fiyat(BelgeKalem.objects.first()), Decimal("5000.0000"))      # 0 -> tutar ÷ miktar
        self.assertEqual(self.client.get(reverse("malzemeler")).status_code, 200)
        self.assertEqual(self.client.get(reverse("malzeme_detay", args=[m.pk])).status_code, 200)

    def test_degisim_sifira_bolmez(self):
        self.assertIsNone(ms._degisim(Decimal(5), Decimal(0)))
        self.assertIsNone(ms._degisim(Decimal(5), Decimal(-1)))


class CiftGirisKdvTests(Temel):
    def test_kdvli_giriste_de_cift_giris_uyarilir(self):
        d = dict(tutar_kurus="100,00", kdv_modu="HARIC", kdv_orani="20", evrak_no="1")
        self.assertEqual(self.post(**d).status_code, 302)
        self.assertEqual(Belge.objects.get().tutar_kurus, 12000)                       # kayıtta KDV'li tutar
        r = self.post(**{**d, "evrak_no": "2"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "zaten var")
        self.assertEqual(Belge.objects.count(), 1)
        self.assertEqual(self.post(**{**d, "evrak_no": "2", "yine_de": "on"}).status_code, 302)

    def test_gecersiz_kdv_iken_cift_giris_kontrolu_cokmez(self):
        self.post(evrak_no="1")
        r = self.post(evrak_no="2", kdv_modu="DAHIL", kdv_orani="-100")
        self.assertEqual(r.status_code, 200)


class KdvSinirTests(Temel):
    def test_sinir_disi_oranlar_500_degil_form_hatasi(self):
        for kw, parca in (({"kdv_modu": "DAHIL", "kdv_orani": "-100"}, "0 ile 100"), ({"kdv_modu": "HARIC", "kdv_orani": "-500"}, "0 ile 100"),
                          ({"kdv_modu": "HARIC", "kdv_orani": "20", "tevkifat_orani": "900"}, "Tevkifat oranı 0 ile 100"),
                          ({"kdv_modu": "HARIC", "kdv_orani": "101"}, "0 ile 100")):
            r = self.post(**kw)
            self.assertEqual(r.status_code, 200, kw)
            self.assertContains(r, parca)
        self.assertEqual(Belge.objects.count(), 0)

    def test_sinirlar_kendisi_gecerli(self):
        self.assertEqual(self.post(kdv_modu="HARIC", kdv_orani="0", evrak_no="a").status_code, 302)
        self.assertEqual(self.post(kdv_modu="HARIC", kdv_orani="100", tevkifat_orani="100", evrak_no="b", tutar_kurus="7,00").status_code, 302)

    def test_kasa_formu_da_ayni_sekilde_korunur(self):
        ofis = Hesap.objects.get(ad="Ofis Kasa")
        r = self.client.post(f"{reverse('kasa')}?hesap={ofis.pk}", {"tarih": date.today().isoformat(), "yon": "GIRIS", "tutar_kurus": "10,00",
                                                                     "kdv_modu": "DAHIL", "kdv_orani": "-100"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(KasaHareketi.objects.count(), 0)

    def test_model_dogrulamasi_yonetim_icin(self):
        b = Belge(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 1), tutar_kurus=100, kdv_modu="DAHIL", kdv_orani=Decimal("-100"))
        with self.assertRaises(ValidationError):
            b.full_clean()


class TutarSiniriTests(Temel):
    def test_ayristirici_ust_siniri(self):
        self.assertEqual(tl_ayristir("100.000.000.000,00"), MAKS_KURUS)
        with self.assertRaises(ValueError):
            tl_ayristir("100.000.000.000,01")
        with self.assertRaises(ValueError):
            tl_ayristir("92.233.720.368.547.758,07")

    def test_belge_formu_ve_gider_reddeder(self):
        r = self.post(tutar_kurus="92.233.720.368.547.758,07")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Belge.objects.count(), 0)
        kat = GiderKategori.objects.get(ad="Kira")
        with self.assertRaises(ValidationError):
            gs.kaydet(2026, 1, {f"tutar_{kat.pk}": "999.999.999.999.999,00"}, [kat])

    def test_model_dogrudan_dogrulanir(self):
        b = Belge(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 1), tutar_kurus=10**15)
        with self.assertRaises(ValidationError):
            b.full_clean()


class IntegrityTests(Temel):
    def test_esik_zamanli_cift_gonderimde_500_degil_hata(self):
        with mock.patch("defter.forms.BelgeForm.save", side_effect=IntegrityError("UNIQUE")):
            r = self.post(evrak_no="77")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "az önce başka bir kayıtla girildi")


class GuvenliIntTests(SimpleTestCase):
    def test_bozuk_girdiler(self):
        for v in ("²", "abc", "", None, "1e3", "-5", "99999999999999999999", "1.5", " "):
            self.assertIsNone(metin.guvenli_int(v), repr(v))
        self.assertEqual(metin.guvenli_int("12"), 12)
        self.assertEqual(metin.guvenli_int(" 7 "), 7)
        self.assertEqual(metin.guvenli_int("0"), 0)


class GuvenliIntSayfaTests(Temel):
    def test_ussu_ve_benzeri_parametreler_500_vermez(self):
        self.client.force_login(rol_kullanici("y", is_superuser=True, is_staff=True))
        for url in ("/?cari=²", "/takvim/?cari=²", "/kasa/?kategori=²", "/kasa/?hesap=²", "/gunluk/?nesne=²",
                    "/malzemeler/?kategori=²", "/odemeler/?cari=²", "/tedarikciler/?sira=²"):
            self.assertIn(self.client.get(url).status_code, (200, 302), url)

    def test_post_alanlari(self):
        m = Malzeme.objects.create(ad="X")
        for veri in ({"eylem": "toplu_ata", "kategori_toplu": "²", "sec": ["²", str(m.pk)]},
                     {"eylem": "kategori_kaydet", "idler": ["²", str(m.pk)], f"kategori_{m.pk}": "²"}):
            self.assertEqual(self.client.post(reverse("malzemeler"), veri).status_code, 302)
        r = self.client.post(reverse("malzeme_detay", args=[m.pk]), {"eylem": "birlestir", "hedef": "²"}, follow=True)
        self.assertContains(r, "Birleştirilecek malzemeyi seçin")
        self.assertEqual(self.client.post(reverse("malzeme_detay", args=[m.pk]), {"eylem": "duzenle", "ad": "X", "kategori": "²"}).status_code, 302)


class KatlaBenzersizTests(TestCase):
    def test_model_duzeyinde_yonetim_dahil(self):
        Cari.objects.create(unvan="ERÖZ")
        with self.assertRaises(ValidationError):
            Cari(unvan="Eroz").full_clean()
        Malzeme.objects.create(ad="Işık")
        with self.assertRaises(ValidationError):
            Malzeme(ad="ISIK").full_clean()
        GiderKategori.objects.create(ad="Özel")
        with self.assertRaises(ValidationError):
            GiderKategori(ad="OZEL").full_clean()
        MalzemeKategori.objects.create(ad="Çelik")
        with self.assertRaises(ValidationError):
            MalzemeKategori(ad="celik").full_clean()

    def test_kendini_ve_farkli_adlari_engellemez(self):
        c = Cari.objects.create(unvan="Güneş")
        c.full_clean()                                   # kendi kaydı çakışma sayılmaz
        Cari(unvan="Gün").full_clean()

    def test_yonetim_panelinden_ikinci_ayni_tedarikci_reddedilir(self):
        Cari.objects.create(unvan="ERÖZ HIRDAVAT")
        self.client.force_login(rol_kullanici("y", is_superuser=True, is_staff=True))
        r = self.client.post(reverse("admin:defter_cari_add"), {"unvan": "Eröz Hırdavat", "tur": "TEDARIKCI", "aktif": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "zaten kayıtlı")
        self.assertEqual(Cari.objects.count(), 1)


class TurkceSiralamaTests(TestCase):
    ADLAR = ["Zeytin", "Çelik", "Ahmet", "Şahin", "İnci", "Ömer", "Ulaş", "Üzüm"]

    def test_yardimci(self):
        self.assertEqual(metin.turkce_sirala(self.ADLAR), ["Ahmet", "Çelik", "İnci", "Ömer", "Şahin", "Ulaş", "Üzüm", "Zeytin"])

    def test_secici_kutulari_alfabetik(self):
        for ad in self.ADLAR:
            Cari.objects.create(unvan=ad)
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        beklenen = ["Ahmet", "Çelik", "İnci", "Ömer", "Şahin", "Ulaş", "Üzüm", "Zeytin"]
        for url in ("dashboard", "odeme_listesi", "odeme_takvimi"):
            adlar = [c.unvan for c in self.client.get(reverse(url)).context["cariler"]]
            self.assertEqual(adlar, beklenen, url)

    def test_malzeme_listesi(self):
        for ad in ("Zımba", "Çivi", "Ağaç"):
            Malzeme.objects.create(ad=ad)
        self.assertEqual([m["ad"] for m in ms.hafiza_verisi()], ["Ağaç", "Çivi", "Zımba"])


class SqliteUriTests(YedekTemel):
    def test_ozel_karakterli_yol(self):
        for ad in ("Cari #2", "Yuzde%41", "Soru?x", "Bosluk ve ç"):
            klasor = self.kok / ad
            klasor.mkdir()
            from .test_yedek import sqlite_olustur
            sqlite_olustur(klasor / "cari.sqlite3", cari=4).close()
            self.assertEqual(yd._butunluk(klasor / "cari.sqlite3"), "ok", ad)
            self.assertEqual(yd._sayilar(klasor / "cari.sqlite3")["cari"], 4, ad)

    def test_ayni_adli_baska_veritabani_okunmaz(self):
        """'#' sonrası kesilen yol, 'Cari ' adlı yanlış bir dosyaya bakardı."""
        from .test_yedek import sqlite_olustur
        (self.kok / "Cari #2").mkdir()
        sqlite_olustur(self.kok / "Cari #2" / "cari.sqlite3", cari=9).close()
        self.assertEqual(yd._sayilar(self.kok / "Cari #2" / "cari.sqlite3")["cari"], 9)


class GeriYuklemeManifestTests(YedekTemel):
    def test_manifestte_olmayan_uye_geri_yuklenmez(self):
        z = self.yap()
        self.zip_yeniden_yaz(z, lambda u: u.__setitem__("ekler/ekstra.png", PNG))
        d = yd.yedek_dogrula(z)
        self.assertTrue(d.ok)                                                           # yalnızca uyarı
        hedef = self.kok / "geri"
        yd.geri_yukle(z, hedef)
        self.assertTrue((hedef / "ekler" / "ab" / "dosya1.png").is_file())
        self.assertFalse((hedef / "ekler" / "ekstra.png").exists())


class BulVeyaOlusturHaritaTests(TestCase):
    def test_harita_ile_tablo_taranmaz(self):
        for i in range(50):
            Malzeme.objects.create(ad=f"Malzeme {i}")
        harita = ms.katla_haritasi()
        with self.assertNumQueries(0):
            for i in range(50):
                m, yeni = ms.malzeme_bul_veya_olustur(f"malzeme {i}", harita=harita)
                self.assertFalse(yeni)

    def test_yeni_malzeme_haritaya_eklenir_ve_tekrar_olusmaz(self):
        h = ms.katla_haritasi()
        a, y1 = ms.malzeme_bul_veya_olustur("Yeni Ürün", "adet", h)
        b, y2 = ms.malzeme_bul_veya_olustur("yeni ürün", "", h)
        self.assertEqual((y1, y2, a.pk), (True, False, b.pk))
        self.assertEqual(Malzeme.objects.count(), 1)


class MalzemeSayfalamaTests(TestCase):
    def setUp(self):
        Malzeme.objects.bulk_create([Malzeme(ad=f"M{i:04d}") for i in range(250)])
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.url = reverse("malzemeler")

    def test_sayfalar(self):
        r = self.client.get(self.url)
        self.assertEqual((len(r.context["satirlar"]), r.context["bulunan"], r.context["sayfa_nesnesi"].paginator.num_pages), (100, 250, 3))
        self.assertContains(r, "sayfa 1 / 3")
        r = self.client.get(self.url, {"sayfa": 3})
        self.assertEqual(len(r.context["satirlar"]), 50)
        self.assertContains(r, "sayfa=2")                                                 # önceki bağlantısı

    def test_bozuk_sayfa_ve_suzgec_korunur(self):
        for s in ("x", "0", "-1", "999", "²"):
            self.assertEqual(self.client.get(self.url, {"sayfa": s}).status_code, 200, s)
        r = self.client.get(self.url, {"q": "M0", "sayfa": 2})
        self.assertContains(r, "q=M0&sayfa=3")


class BelgelerTests(SimpleTestCase):
    def test_kur_bat_yonetici_varsa_sormaz_ve_py312(self):
        b = (Path(__file__).resolve().parent.parent / "kur.bat").read_bytes()
        self.assertTrue(b.isascii() and b"\r\n" in b)
        t = b.decode("ascii")
        self.assertIn("filter(is_superuser=True).exists()", t)
        self.assertIn("(3,12)", t)
        self.assertEqual(t.count("createsuperuser"), 1)

    def test_django_surumu_python_ile_uyumlu_sabitlendi(self):
        r = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
        self.assertIn("Django>=6.0", r)
