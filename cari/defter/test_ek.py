import os
import re
import tempfile
import zipfile
from datetime import date
from io import BytesIO, StringIO

import openpyxl
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from . import ek_servisi as es
from .models import Belge, Cari, Ek, EkstreMutabakat, Hesap, KasaHareketi

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
PDF = b"%PDF-1.4\n%fake\n" + b"x" * 40
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 20
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20


def xlsx_bayt():
    b = BytesIO()
    openpyxl.Workbook().save(b)
    return b.getvalue()


def docx_bayt():
    b = BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w/>")
    return b.getvalue()


def dosya(ad, icerik):
    return SimpleUploadedFile(ad, icerik)


class EkTemel(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        ayar = override_settings(EK_DIZINI=self._tmp.name)
        ayar.enable()
        self.addCleanup(ayar.disable)
        self.cari = Cari.objects.create(unvan="EK CARİ")
        self.belge = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 5),
                                          tutar_kurus=1000, evrak_no="001")
        self.kasa = Hesap.objects.get(ad="Ofis Kasa")
        self.hareket = KasaHareketi.objects.create(hesap=self.kasa, yon="GIRIS", tutar_kurus=500, tarih=date(2026, 1, 5))
        self.mut = EkstreMutabakat.objects.create(cari=self.cari, ekstre_tarihi=date(2026, 1, 31),
                                                  ekstre_bakiye_kurus=1000)

    def depo_dosyalari(self):
        return [p for p in os.scandir(self._tmp.name) for p in ([p] if p.is_file() else os.scandir(p.path))]


class DogrulamaTests(EkTemel):
    def test_gecerli_turler_kabul_edilir(self):
        for ad, icerik, tur in (("a.png", PNG, "image/png"), ("a.jpg", JPG, "image/jpeg"),
                                ("a.jpeg", JPG + b"2", "image/jpeg"), ("a.gif", GIF, "image/gif"),
                                ("a.webp", WEBP, "image/webp"), ("a.pdf", PDF, "application/pdf"),
                                ("a.xlsx", xlsx_bayt(), es.XLSX), ("a.docx", docx_bayt(), es.DOCX)):
            ek = es.ek_ekle(self.cari, dosya(ad, icerik))
            self.assertEqual(ek.icerik_turu, tur, ad)

    def test_kunye_ve_hash_yolu(self):
        ek = es.ek_ekle(self.belge, dosya("Fiş 001.PNG", PNG), "  fiş görseli ", "ali")
        self.assertEqual((ek.orijinal_ad, ek.boyut_bayt, ek.aciklama, ek.yukleyen), ("Fiş 001.PNG", len(PNG), "fiş görseli", "ali"))
        import hashlib
        self.assertEqual(ek.sha256, hashlib.sha256(PNG).hexdigest())
        self.assertRegex(ek.yol, r"^[0-9a-f]{2}/[0-9a-f]{64}\.png$")      # yol YALNIZCA hash'ten gelir
        self.assertEqual(es.depo_yolu(ek).read_bytes(), PNG)

    def test_jpeg_uzantisi_jpg_olarak_saklanir(self):
        self.assertTrue(es.ek_ekle(self.cari, dosya("x.jpeg", JPG)).yol.endswith(".jpg"))

    def test_yasak_turler_reddedilir(self):
        for ad, icerik in (("a.exe", b"MZ\x90\x00"), ("a.html", b"<script>alert(1)</script>"),
                           ("a.svg", b"<svg onload=alert(1)/>"), ("a.js", b"alert(1)"), ("a.php", b"<?php"),
                           ("a", PNG), ("a.png.exe", PNG), ("a.zip", b"PK\x03\x04")):
            with self.assertRaises(es.EkHatasi, msg=ad):
                es.ek_ekle(self.cari, dosya(ad, icerik))
        self.assertEqual(Ek.objects.count(), 0)
        self.assertEqual(self.depo_dosyalari(), [])

    def test_uzanti_ile_icerik_uyusmali(self):
        for ad, icerik in (("a.pdf", PNG), ("a.png", b"<html><script>x</script></html>"), ("a.jpg", PDF),
                           ("a.png", PDF), ("a.gif", PNG), ("a.webp", PNG),
                           ("a.xlsx", b"duz metin"), ("a.xlsx", b"PK\x03\x04bozuk"), ("a.docx", PNG)):
            with self.assertRaises(es.EkHatasi, msg=ad) as m:
                es.ek_ekle(self.cari, dosya(ad, icerik))
            self.assertIn("uyuşmuyor", str(m.exception))

    def test_zip_icerigi_ofis_dosyasi_degilse_xlsx_olamaz(self):
        b = BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("rastgele.txt", "x")
        with self.assertRaises(es.EkHatasi):
            es.ek_ekle(self.cari, dosya("a.xlsx", b.getvalue()))

    def test_bos_ve_buyuk_dosya(self):
        with self.assertRaises(es.EkHatasi) as m:
            es.ek_ekle(self.cari, dosya("a.png", b""))
        self.assertIn("boş", str(m.exception))
        with override_settings(EK_MAX_BAYT=100):
            with self.assertRaises(es.EkHatasi) as m:
                es.ek_ekle(self.cari, dosya("a.png", PNG + b"x" * 200))
            self.assertIn("en fazla", str(m.exception))
            es.ek_ekle(self.cari, dosya("a.png", PNG))                       # sınırın altı serbest

    def test_dosya_adi_temizligi(self):
        T = es.temiz_ad
        self.assertEqual(T("../../etc/passwd.png"), "passwd.png")
        self.assertEqual(T("C:\\Users\\x\\fis.pdf"), "fis.pdf")
        self.assertEqual(T("a\x00b\x1f.png"), "ab.png")
        self.assertEqual(T("  ...  "), "dosya")
        self.assertEqual(T(""), "dosya")
        self.assertEqual(T(None), "dosya")
        uzun = T("x" * 500 + ".pdf")
        self.assertLessEqual(len(uzun), 150)
        self.assertTrue(uzun.endswith(".pdf"))

    def test_gezinme_denemesi_depo_disina_yazmaz(self):
        ek = es.ek_ekle(self.cari, dosya("../../../tmp/evil.png", PNG))
        self.assertEqual(ek.orijinal_ad, "evil.png")
        self.assertTrue(str(es.depo_yolu(ek).resolve()).startswith(os.path.realpath(self._tmp.name)))
        self.assertFalse(os.path.exists("/tmp/evil.png"))

    def test_yol_bozulursa_depo_disina_cikilamaz(self):
        from django.core.exceptions import SuspiciousFileOperation
        ek = es.ek_ekle(self.cari, dosya("a.png", PNG))
        ek.yol = "../../etc/passwd"
        with self.assertRaises(SuspiciousFileOperation):
            es.depo_yolu(ek)

    def test_gecici_dosya_kalmaz_ve_izin_0600(self):
        ek = es.ek_ekle(self.cari, dosya("a.png", PNG))
        adlar = [p.name for p in self.depo_dosyalari()]
        self.assertFalse([a for a in adlar if a.endswith(".tmp")])
        if os.name == "posix":
            self.assertEqual(os.stat(es.depo_yolu(ek)).st_mode & 0o777, 0o600)


class SahipVeTekrarTests(EkTemel):
    def test_dort_sahip_turu(self):
        for sahip, alan in ((self.belge, "belge"), (self.hareket, "kasa_hareketi"),
                            (self.mut, "mutabakat"), (self.cari, "cari")):
            ek = es.ek_ekle(sahip, dosya(f"{alan}.png", PNG + alan.encode()))
            self.assertEqual(ek.sahip, sahip)
            self.assertEqual(ek.sahip_turu, alan)

    def test_desteklenmeyen_sahip(self):
        with self.assertRaises(es.EkHatasi):
            es.ek_ekle(self.kasa, dosya("a.png", PNG))

    def test_veritabani_tek_sahip_kuralini_zorlar(self):
        ortak = dict(orijinal_ad="a.png", icerik_turu="image/png", boyut_bayt=1, sha256="0" * 64, yol="00/x.png")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ek.objects.create(**ortak)                                        # sahipsiz
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ek.objects.create(belge=self.belge, cari=self.cari, **ortak)      # iki sahipli

    def test_ayni_dosya_ayni_kayda_iki_kez_eklenmez(self):
        es.ek_ekle(self.belge, dosya("a.png", PNG))
        with self.assertRaises(es.EkHatasi) as m:
            es.ek_ekle(self.belge, dosya("baska-ad.png", PNG))
        self.assertIn("zaten ekli", str(m.exception))

    def test_ayni_icerik_baska_kayda_eklenir_diskte_tek_kopya(self):
        a = es.ek_ekle(self.belge, dosya("a.png", PNG))
        b = es.ek_ekle(self.hareket, dosya("b.png", PNG))
        self.assertEqual(a.yol, b.yol)
        self.assertEqual(len(self.depo_dosyalari()), 1)

    def test_kaldirma_nedeni_ister_dosya_diskte_kalir_ve_tekrar_eklenebilir(self):
        a = es.ek_ekle(self.belge, dosya("a.png", PNG))
        b = es.ek_ekle(self.hareket, dosya("b.png", PNG))
        with self.assertRaises(es.EkHatasi):
            es.ek_kaldir(a, "  ")
        es.ek_kaldir(a, "yanlış fiş")
        a.refresh_from_db()
        self.assertTrue(a.kaldirildi and a.kaldirma_nedeni == "yanlış fiş" and a.kaldirma_zamani)
        self.assertTrue(es.depo_yolu(a).exists())                            # dosya silinmedi
        self.assertEqual(es.depo_yolu(b).read_bytes(), PNG)                  # diğer ek etkilenmedi
        with self.assertRaises(es.EkHatasi):
            es.ek_kaldir(a, "tekrar")
        self.assertEqual(list(es.ekleri_listele(self.belge)), [])
        self.assertEqual(es.ekleri_listele(self.belge, kaldirilanlar=True).count(), 1)
        es.ek_ekle(self.belge, dosya("a.png", PNG))                          # kaldırılan tekrar eklenebilir

    def test_ek_sayilari(self):
        es.ek_ekle(self.belge, dosya("a.png", PNG))
        es.ek_ekle(self.belge, dosya("b.png", PNG + b"1"))
        k = es.ek_ekle(self.belge, dosya("c.png", PNG + b"2"))
        es.ek_kaldir(k, "x")
        self.assertEqual(es.ek_sayilari([self.belge.pk], "belge"), {self.belge.pk: 2})


class DepoButunlukTests(EkTemel):
    def test_temiz_depo(self):
        es.ek_ekle(self.belge, dosya("a.png", PNG))
        s = es.depo_dogrula()
        self.assertEqual((s["eksik"], s["bozuk"], s["yetim"], s["toplam"]), ([], [], [], 1))

    def test_eksik_bozuk_ve_yetim(self):
        a = es.ek_ekle(self.belge, dosya("a.png", PNG))
        b = es.ek_ekle(self.belge, dosya("b.png", PNG + b"1"))
        es.ek_ekle(self.belge, dosya("c.png", PNG + b"2"))
        os.remove(es.depo_yolu(a))                                           # eksik
        with open(es.depo_yolu(b), "ab") as f:
            f.write(b"bozuldu")                                              # bozuk
        yetim = os.path.join(self._tmp.name, "ff")
        os.makedirs(yetim)
        open(os.path.join(yetim, "kayitsiz.png"), "wb").write(PNG)           # kayıtsız
        s = es.depo_dogrula()
        self.assertEqual([e.pk for e in s["eksik"]], [a.pk])
        self.assertEqual([e.pk for e in s["bozuk"]], [b.pk])
        self.assertEqual([p.name for p in s["yetim"]], ["kayitsiz.png"])

    def test_komut(self):
        es.ek_ekle(self.belge, dosya("a.png", PNG))
        out = StringIO()
        call_command("ekleri_dogrula", stdout=out)
        self.assertIn("Depo tutarlı", out.getvalue())
        ek = Ek.objects.get()
        os.remove(es.depo_yolu(ek))
        with self.assertRaises(CommandError):
            call_command("ekleri_dogrula", stdout=StringIO(), stderr=StringIO())


class EkEkranTests(EkTemel):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("p", password="x", is_staff=True)
        self.client.force_login(self.user)

    def url(self, tur="belge", pk=None):
        return reverse("ek_sahip", args=[tur, pk or self.belge.pk])

    def test_giris_gerekli(self):
        ek = es.ek_ekle(self.belge, dosya("a.png", PNG))
        self.client.logout()
        for u in (self.url(), reverse("ek_depo"), reverse("ek_indir", args=[ek.pk])):
            r = self.client.get(u)
            self.assertEqual(r.status_code, 302, u)
            self.assertIn("/admin/login/", r["Location"])
        self.assertEqual(self.client.post(reverse("ek_kaldir", args=[ek.pk]), {"neden": "x"}).status_code, 302)
        self.assertTrue(Ek.objects.filter(pk=ek.pk, kaldirildi=False).exists())
        self.assertEqual(self.client.post(self.url(), {"dosyalar": dosya("z.png", PNG)}).status_code, 302)
        self.assertEqual(Ek.objects.count(), 1)

    def test_staff_olmayan_giremez(self):
        sade = get_user_model().objects.create_user("s", password="x", is_staff=False)
        self.client.force_login(sade)
        ek = es.ek_ekle(self.belge, dosya("a.png", PNG))
        self.assertEqual(self.client.get(reverse("ek_indir", args=[ek.pk])).status_code, 302)

    def test_sayfalar_ve_bilinmeyen_sahip(self):
        for tur, pk in (("belge", self.belge.pk), ("kasa", self.hareket.pk), ("mutabakat", self.mut.pk),
                        ("cari", self.cari.pk)):
            self.assertEqual(self.client.get(self.url(tur, pk)).status_code, 200, tur)
        self.assertEqual(self.client.get(self.url("hesap", 1)).status_code, 404)
        self.assertEqual(self.client.get(self.url("belge", 999999)).status_code, 404)

    def test_coklu_yukleme_gecerli_ve_gecersiz_karisik(self):
        r = self.client.post(self.url(), {"dosyalar": [dosya("a.png", PNG), dosya("kotu.exe", b"MZ"),
                                                       dosya("b.pdf", PDF)], "aciklama": "fiş"}, follow=True)
        self.assertContains(r, "2 dosya eklendi")
        self.assertContains(r, "kotu.exe")
        self.assertContains(r, "izin verilmiyor")
        self.assertEqual(Ek.objects.count(), 2)
        self.assertEqual(Ek.objects.first().yukleyen, "p")

    def test_dosya_secilmedi_ve_adet_siniri(self):
        self.assertContains(self.client.post(self.url(), {}, follow=True), "Dosya seçilmedi")
        with override_settings(EK_MAX_ADET=2):
            r = self.client.post(self.url(), {"dosyalar": [dosya(f"{i}.png", PNG + bytes([i])) for i in range(3)]},
                                 follow=True)
        self.assertContains(r, "en fazla 2 dosya")
        self.assertEqual(Ek.objects.count(), 0)

    def test_indirme_icerik_turu_ve_basliklar(self):
        png = es.ek_ekle(self.belge, dosya("Fiş şüğ.png", PNG))
        pdf = es.ek_ekle(self.belge, dosya("e.pdf", PDF))
        xl = es.ek_ekle(self.belge, dosya("t.xlsx", xlsx_bayt()))
        r = self.client.get(reverse("ek_indir", args=[png.pk]))
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        self.assertEqual(b"".join(r.streaming_content), PNG)
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", r["Cache-Control"])
        self.assertTrue(r["Content-Disposition"].startswith("inline"))
        self.assertIn("filename*=utf-8", r["Content-Disposition"].lower())        # Türkçe karakterli ad
        self.assertTrue(self.client.get(reverse("ek_indir", args=[pdf.pk]))["Content-Disposition"].startswith("inline"))
        self.assertTrue(self.client.get(reverse("ek_indir", args=[xl.pk]))["Content-Disposition"].startswith("attachment"))
        self.assertTrue(self.client.get(reverse("ek_indir", args=[png.pk]) + "?indir=1")["Content-Disposition"]
                        .startswith("attachment"))

    def test_kaldirilan_veya_diskte_olmayan_indirilemez(self):
        a = es.ek_ekle(self.belge, dosya("a.png", PNG))
        b = es.ek_ekle(self.belge, dosya("b.png", PNG + b"1"))
        os.remove(es.depo_yolu(b))
        self.assertEqual(self.client.get(reverse("ek_indir", args=[b.pk])).status_code, 404)
        es.ek_kaldir(a, "x")
        self.assertEqual(self.client.get(reverse("ek_indir", args=[a.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("ek_indir", args=[999999])).status_code, 404)

    def test_kaldirma_ekrani(self):
        ek = es.ek_ekle(self.belge, dosya("a.png", PNG))
        u = reverse("ek_kaldir", args=[ek.pk])
        self.assertEqual(self.client.get(u).status_code, 405)
        r = self.client.post(u, {"neden": ""}, follow=True)
        self.assertContains(r, "Kaldırma nedeni")
        ek.refresh_from_db()
        self.assertFalse(ek.kaldirildi)
        r = self.client.post(u, {"neden": "yanlış belge"}, follow=True)
        self.assertContains(r, "Kaldırılan ekler (1)")
        self.assertContains(r, "yanlış belge")
        self.assertEqual(r.redirect_chain[-1][0], self.url())

    def test_dosya_adi_html_kacisi(self):
        es.ek_ekle(self.belge, dosya("<i onclick=alert(1)>x.png", PNG))
        r = self.client.get(self.url())
        self.assertContains(r, "&lt;i onclick=alert(1)&gt;x.png")
        self.assertNotContains(r, "<i onclick")
        self.assertContains(self.client.get(reverse("ek_depo")), "&lt;i onclick=alert(1)&gt;x.png")

    def test_depo_sayfasi_filtreler(self):
        es.ek_ekle(self.belge, dosya("fis-001.png", PNG), "ocak fişi")
        es.ek_ekle(self.hareket, dosya("makbuz.pdf", PDF))
        k = es.ek_ekle(self.mut, dosya("ekstre.pdf", PDF + b"1"))
        es.ek_kaldir(k, "yanlış")
        r = self.client.get(reverse("ek_depo"))
        self.assertContains(r, "fis-001.png")
        self.assertContains(r, "makbuz.pdf")
        self.assertNotContains(r, "ekstre.pdf")
        self.assertContains(self.client.get(reverse("ek_depo"), {"kaldirilan": "1"}), "ekstre.pdf")
        self.assertContains(self.client.get(reverse("ek_depo"), {"q": "ocak"}), "fis-001.png")
        self.assertNotContains(self.client.get(reverse("ek_depo"), {"q": "ocak"}), "makbuz.pdf")
        self.assertContains(self.client.get(reverse("ek_depo"), {"q": "EK CARİ"}), "fis-001.png")   # cari adıyla ara
        self.assertNotContains(self.client.get(reverse("ek_depo"), {"tur": "kasa"}), "fis-001.png")
        self.assertContains(self.client.get(reverse("ek_depo"), {"tur": "kasa"}), "makbuz.pdf")
        for kotu in ({"bas": "abc"}, {"bit": "31.02.2026"}, {"sayfa": "99"}, {"tur": "x"}):
            self.assertEqual(self.client.get(reverse("ek_depo"), kotu).status_code, 200, kotu)

    def test_diger_ekranlarda_ek_baglantilari(self):
        es.ek_ekle(self.belge, dosya("a.png", PNG))
        es.ek_ekle(self.mut, dosya("e.pdf", PDF))
        es.ek_ekle(self.hareket, dosya("m.png", PNG + b"1"))
        r = self.client.get(reverse("cari_ekstre", args=[self.cari.pk]))
        self.assertContains(r, reverse("ek_sahip", args=["belge", self.belge.pk]))
        self.assertContains(r, "Cari dosyaları (0)")
        r = self.client.get(reverse("mutabakat_detay", args=[self.mut.pk]))
        self.assertContains(r, "Ekler (1)")
        r = self.client.get(reverse("kasa"))
        self.assertContains(r, reverse("ek_sahip", args=["kasa", self.hareket.pk]))

    def test_yonetim_ekranlari(self):
        admin = get_user_model().objects.create_superuser("a", password="Guclu-Parola-9")
        self.client.force_login(admin)
        ek = es.ek_ekle(self.belge, dosya("a.png", PNG))
        self.assertEqual(self.client.get(reverse("admin:defter_ek_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:defter_ek_add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:defter_ek_delete", args=[ek.pk]), {"post": "yes"}).status_code, 403)
        r = self.client.get(reverse("admin:defter_belge_change", args=[self.belge.pk]))
        self.assertContains(r, "Ekler (1)")
        for ad, pk in (("cari", self.cari.pk), ("kasahareketi", self.hareket.pk), ("ekstremutabakat", self.mut.pk)):
            self.assertContains(self.client.get(reverse(f"admin:defter_{ad}_change", args=[pk])), "Ekler (")
        self.assertContains(self.client.get(reverse("admin:defter_belge_add")), "önce kaydedin")


class FisGorselleriKomutuTests(EkTemel):
    def setUp(self):
        super().setUp()
        self._girdi = tempfile.TemporaryDirectory()          # kaynak dosyalar depo dizininden AYRI
        self.addCleanup(self._girdi.cleanup)

    def zip_yaz(self, uyeler):
        yol = os.path.join(self._girdi.name, "fisler.zip")
        with zipfile.ZipFile(yol, "w") as z:
            for ad, veri in uyeler.items():
                z.writestr(ad, veri)
        return yol

    def calistir(self, *args):
        out, err = StringIO(), StringIO()
        try:
            call_command("fis_gorselleri_ekle", *args, stdout=out, stderr=err)
        finally:
            self.cikti = out.getvalue() + err.getvalue()

    def test_zip_eslestirme_sifirli_ad_ve_eslesmeyen(self):
        b2 = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 6), tutar_kurus=5, evrak_no="002")
        yol = self.zip_yaz({"001.png": PNG, "2.png": PNG + b"1", "999.png": PNG + b"2", "klasor/": b""})
        self.calistir(yol, "--cari", "EK CARİ")
        self.assertIn("Eklendi: 2", self.cikti)
        self.assertIn("eşleşmedi: 1", self.cikti)
        self.assertEqual(self.belge.ekler.count(), 1)
        self.assertEqual(b2.ekler.count(), 1)                                 # "2.png" -> "002"
        self.assertEqual(self.belge.ekler.get().yukleyen, "toplu aktarım")

    def test_tekrar_calistirma_guvenli_ve_deneme_hicbir_sey_yazmaz(self):
        yol = self.zip_yaz({"001.png": PNG})
        self.calistir(yol, "--cari", "EK CARİ", "--deneme")
        self.assertEqual(Ek.objects.count(), 0)
        self.assertEqual(self.depo_dosyalari(), [])
        self.calistir(yol, "--cari", "EK CARİ")
        self.calistir(yol, "--cari", "EK CARİ")
        self.assertIn("zaten ekli: 1", self.cikti)
        self.assertEqual(Ek.objects.count(), 1)

    def test_iptal_belgeye_bagIanmaz(self):
        Belge.objects.filter(pk=self.belge.pk).update(iptal=True, iptal_nedeni="x")
        self.calistir(self.zip_yaz({"001.png": PNG}), "--cari", "EK CARİ")
        self.assertIn("eşleşmedi: 1", self.cikti)
        self.assertEqual(Ek.objects.count(), 0)

    def test_gecersiz_dosya_hata_verir_digerleri_eklenir(self):
        yol = self.zip_yaz({"001.png": b"png degil"})
        with self.assertRaises(CommandError):
            self.calistir(yol, "--cari", "EK CARİ")
        self.assertIn("uyuşmuyor", self.cikti)

    def test_klasor_modu(self):
        klasor = os.path.join(self._girdi.name, "gorseller")
        os.makedirs(klasor)
        open(os.path.join(klasor, "001.png"), "wb").write(PNG)
        self.calistir(klasor, "--cari", "EK CARİ")
        self.assertEqual(self.belge.ekler.count(), 1)

    def test_yol_gezinme_adli_uye_depo_disina_yazmaz(self):
        yol = self.zip_yaz({"../../001.png": PNG})
        self.calistir(yol, "--cari", "EK CARİ")
        self.assertEqual(self.belge.ekler.count(), 1)                         # adın son bileşeni '001.png'
        self.assertTrue(es.depo_yolu(self.belge.ekler.get()).resolve().is_relative_to(os.path.realpath(self._tmp.name)))
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, "..", "..", "001.png")))

    def test_hatali_girdiler(self):
        with self.assertRaises(CommandError):
            self.calistir(self.zip_yaz({"001.png": PNG}), "--cari", "YOK BÖYLE CARİ")
        with self.assertRaises(CommandError):
            self.calistir("/yok/boyle/yol.zip", "--cari", "EK CARİ")
        duz = os.path.join(self._girdi.name, "metin.txt")
        open(duz, "w").write("zip degil")
        with self.assertRaises(CommandError):
            self.calistir(duz, "--cari", "EK CARİ")
