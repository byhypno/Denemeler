import re
from datetime import date
from pathlib import Path

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from . import gunluk
from . import kasa_servisi as ks
from .test_yardimci import cari_kasa_ac
from .excel_aktar import ice_aktar
from .models import Belge, Cari, Ek, GunSonu, Hesap, IslemGunlugu, KasaHareketi
from .tests import _ornek_excel

BASE = Path(__file__).resolve().parent


class GunlukTemel(TestCase):
    def son(self, **filtre):
        return IslemGunlugu.objects.filter(**filtre).first()

    def adet(self, **filtre):
        return IslemGunlugu.objects.filter(**filtre).count()

    def belge(self, **kw):
        c = kw.pop("cari", None) or Cari.objects.get_or_create(unvan="X")[0]
        return Belge.objects.create(cari=c, tur="ALIS_FISI", tarih=date(2026, 1, 5), tutar_kurus=100000,
                                    evrak_no=kw.pop("evrak_no", "1"), **kw)


class KayitGunluguTests(GunlukTemel):
    def test_olusturma_okunur_alanlarla_yazilir(self):
        b = self.belge()
        g = self.son(model="Belge")
        self.assertEqual((g.islem, g.nesne_id, g.kullanici), ("OLUSTURDU", b.pk, "sistem"))
        self.assertEqual(g.degisiklik["Tutar (₺)"], [None, "1.000,00 ₺"])
        self.assertEqual(g.degisiklik["Cari"], [None, "X"])
        self.assertEqual(g.degisiklik["Evrak türü"], [None, "Alış Fişi"])
        self.assertEqual(g.degisiklik["KDV girişi"], [None, "KDV bilinmiyor"])
        self.assertNotIn("İptal", g.degisiklik)                       # boş/False alanlar gürültü yapmaz
        self.assertIn("Alış Fişi", g.nesne_ozeti)

    def test_degisiklikte_yalniz_degisen_alan_eski_ve_yeni(self):
        b = self.belge()
        b.tutar_kurus = 120050
        b.aciklama = "düzeltildi"
        b.save()
        g = self.son(islem="DEGISTI")
        self.assertEqual(g.degisiklik, {"Tutar (₺)": ["1.000,00 ₺", "1.200,50 ₺"], "Açıklama": [None, "düzeltildi"]})

    def test_degisiklik_yoksa_kayit_yok(self):
        b = self.belge()
        n = self.adet()
        b.save()
        b.save()
        self.assertEqual(self.adet(), n)

    def test_iptal_ayri_islem_olarak(self):
        b = self.belge()
        b.iptal, b.iptal_nedeni = True, "yanlış giriş"
        b.save()
        g = self.son(islem="IPTAL")
        self.assertEqual(g.degisiklik["İptal"], ["Hayır", "Evet"])
        self.assertEqual(g.degisiklik["İptal nedeni"], [None, "yanlış giriş"])

    def test_silme(self):
        b = self.belge()
        pk = b.pk
        b.delete()
        g = self.son(islem="SILINDI", model="Belge")
        self.assertEqual(g.nesne_id, pk)
        self.assertEqual(g.degisiklik["Tutar (₺)"], ["1.000,00 ₺", None])

    def test_kasa_ve_gun_sonu_kilidi(self):
        kasa = Hesap.objects.get(ad="Ofis Kasa")
        KasaHareketi.objects.create(hesap=kasa, yon="GIRIS", tutar_kurus=5000, tarih=date(2026, 3, 1))
        self.assertEqual(self.son(model="KasaHareketi").degisiklik["Yön"], [None, "Giriş"])
        g = ks.gun_sonu_kapat(kasa, date(2026, 3, 1), 5000, bugun=date(2026, 3, 2))
        self.assertEqual(self.son(model="GunSonu", islem="OLUSTURDU").nesne_id, g.pk)
        g.kilitli = False                                              # kilit kaldırma KAYIT ALTINDA
        g.save()
        kilit = self.son(model="GunSonu", islem="DEGISTI")
        self.assertEqual(kilit.degisiklik, {"Kilitli": ["Evet", "Hayır"]})

    def test_ek_kaldirma(self):
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from . import ek_servisi as es
        with tempfile.TemporaryDirectory() as d, override_settings(EK_DIZINI=d):
            c = Cari.objects.create(unvan="E")
            ek = es.ek_ekle(c, SimpleUploadedFile("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20))
            self.assertEqual(self.son(model="Ek", islem="OLUSTURDU").nesne_id, ek.pk)
            es.ek_kaldir(ek, "yanlış dosya")
            g = self.son(model="Ek", islem="IPTAL")
            self.assertEqual(g.degisiklik["Kaldırıldı"], ["Hayır", "Evet"])
            self.assertTrue(any("nedeni" in alan and v[1] == "yanlış dosya" for alan, v in g.degisiklik.items()))

    def test_eslestirme_acikca_kaydedilir(self):
        ck = cari_kasa_ac()
        c = Cari.objects.create(unvan="K")
        KasaHareketi.objects.create(hesap=ck, yon="GIRIS", tutar_kurus=9000, tarih=date(2026, 1, 1))
        o = Belge.objects.create(cari=c, tur="ODEME", tarih=date(2026, 1, 3), tutar_kurus=500, odeme_sekli="NAKIT")
        h = KasaHareketi.objects.create(hesap=ck, yon="CIKIS", tutar_kurus=500, tarih=date(2026, 1, 3), cari=c)
        with gunluk.kullanici_olarak("ali"):
            ks.eslestir(h.pk, o.pk)
        g = self.son(model="KasaHareketi", islem="DEGISTI")
        self.assertEqual(g.kullanici, "ali")
        self.assertIn("eşleştirildi", g.ayrinti)
        self.assertEqual(g.nesne_id, h.pk)


class KullaniciAtamasiTests(GunlukTemel):
    def test_baglam_yoneticisi(self):
        with gunluk.kullanici_olarak("ali"):
            self.belge()
        self.assertEqual(self.son(model="Belge").kullanici, "ali")
        self.belge(evrak_no="2")
        self.assertEqual(self.son(model="Belge").kullanici, "sistem")        # blok bitince eski değere döner

    def test_istek_uzerinden_yonetim_paneli(self):
        y = get_user_model().objects.create_superuser("yonetici", password="Guclu-Parola-9")
        self.client.force_login(y)
        c = Cari.objects.create(unvan="P")
        r = self.client.post(reverse("admin:defter_belge_add"), {
            "cari": c.pk, "tur": "ALIS_FISI", "tarih": "05.01.2026", "evrak_no": "A1", "harici_evrak_no": "",
            "aciklama": "", "odeme_sekli": "", "kaynak_notu": "", "tutar_kurus": "1.234,50",
            "kdv_modu": "BILINMIYOR", "kalemler-TOTAL_FORMS": "0", "kalemler-INITIAL_FORMS": "0",
            "kalemler-MIN_NUM_FORMS": "0", "kalemler-MAX_NUM_FORMS": "1000"})
        self.assertEqual(r.status_code, 302)
        g = self.son(model="Belge", islem="OLUSTURDU")
        self.assertEqual(g.kullanici, "yonetici")
        self.assertEqual(g.degisiklik["Tutar (₺)"], [None, "1.234,50 ₺"])

    def test_toplu_iptal_tek_tek_kaydedilir(self):
        y = get_user_model().objects.create_superuser("y", password="Guclu-Parola-9")
        self.client.force_login(y)
        a, b = self.belge(evrak_no="1"), self.belge(evrak_no="2")
        r = self.client.post(reverse("admin:defter_belge_changelist"),
                             {"action": "iptal_et", "_selected_action": [a.pk, b.pk]}, follow=True)
        self.assertEqual(r.status_code, 200)
        iptaller = IslemGunlugu.objects.filter(islem="IPTAL", model="Belge")
        self.assertEqual(sorted(g.nesne_id for g in iptaller), sorted([a.pk, b.pk]))
        self.assertTrue(all(g.kullanici == "y" for g in iptaller))


class SessizModTests(GunlukTemel):
    def test_tek_ozet_kaydi(self):
        with gunluk.sessiz("toplu test") as g:
            self.belge(evrak_no="1")
            self.belge(evrak_no="2")
            g["metin"] = "2 belge eklendi"
        self.assertEqual(self.adet(model="Belge"), 0)
        ozet = self.son(islem="OZEL")
        self.assertEqual(ozet.ayrinti, "2 belge eklendi")
        self.belge(evrak_no="3")                                        # sessiz mod bitti, normal kayıt
        self.assertEqual(self.adet(model="Belge", islem="OLUSTURDU"), 1)

    def test_istisna_olursa_ozet_yazilmaz_ve_mod_kapanir(self):
        with self.assertRaises(RuntimeError):
            with gunluk.sessiz("basarisiz"):
                raise RuntimeError("x")
        self.assertEqual(self.adet(islem="OZEL"), 0)
        self.belge()
        self.assertEqual(self.adet(model="Belge"), 1)

    def test_excel_ice_aktarma_tek_kayit(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "ornek.xlsx")
            _ornek_excel(yol)
            ice_aktar(yol)
        self.assertEqual(IslemGunlugu.objects.count(), 1)
        g = IslemGunlugu.objects.get()
        self.assertEqual(g.islem, "OZEL")
        self.assertIn("ornek.xlsx", g.ayrinti)
        self.assertIn("belge 4", g.ayrinti)
        self.assertIn("kalem 3", g.ayrinti)

    def test_basarisiz_ice_aktarma_kaydi(self):
        import os
        import tempfile
        import openpyxl
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "kotu.xlsx")
            _ornek_excel(yol)
            wb = openpyxl.load_workbook(yol)
            wb["Hareketler"]["I6"] = "Azaltır"
            wb.save(yol)
            ice_aktar(yol)
        self.assertEqual(Belge.objects.count(), 0)
        self.assertIn("BAŞARISIZ", IslemGunlugu.objects.get().ayrinti)


class DegistirilemezlikTests(GunlukTemel):
    def setUp(self):
        self.belge()
        self.g = IslemGunlugu.objects.first()

    def test_uygulama_duzeyi(self):
        self.g.kullanici = "baskasi"
        with self.assertRaises(ValidationError):
            self.g.save()
        with self.assertRaises(ValidationError):
            self.g.delete()

    def test_veritabani_duzeyi_tetikleyiciler(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            IslemGunlugu.objects.filter(pk=self.g.pk).update(kullanici="baskasi")
        with self.assertRaises(DatabaseError), transaction.atomic():
            IslemGunlugu.objects.all().delete()
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as c:
                c.execute("DELETE FROM defter_islemgunlugu")
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as c:
                c.execute("UPDATE defter_islemgunlugu SET islem='DEGISTI'")
        self.g.refresh_from_db()
        self.assertEqual(self.g.kullanici, "sistem")


class GirisOlaylariTests(GunlukTemel):
    def test_giris_cikis_ve_hatali_giris(self):
        get_user_model().objects.create_user("ayse", password="Dogru-Parola-1")
        self.assertIsNone(authenticate(username="ayse", password="YANLIS-PAROLA-999"))
        h = self.son(islem="GIRIS_HATASI")
        self.assertEqual(h.kullanici, "ayse")
        self.assertNotIn("YANLIS-PAROLA-999", f"{h.ayrinti}{h.degisiklik}{h.nesne_ozeti}")
        self.assertTrue(self.client.login(username="ayse", password="Dogru-Parola-1"))
        self.assertEqual(self.son(islem="GIRIS").kullanici, "ayse")
        self.client.logout()
        self.assertEqual(self.son(islem="CIKIS").kullanici, "ayse")

    def test_parola_degeri_gunluge_yazilmaz(self):
        u = get_user_model().objects.create_user("veli", password="Gizli-Parola-77")
        g = self.son(model="Kullanıcı", islem="OLUSTURDU")
        self.assertEqual(g.nesne_id, u.pk)
        metin = str(g.degisiklik)
        self.assertNotIn(u.password, metin)
        self.assertNotIn("Gizli-Parola-77", metin)
        self.assertEqual(g.degisiklik["Parola"], [None, "***"])
        u.set_password("Baska-Parola-88")
        u.save()
        d = self.son(model="Kullanıcı", islem="DEGISTI")
        self.assertEqual(d.degisiklik["Parola"], ["***", "***"])
        self.assertNotIn(u.password, str(d.degisiklik))


class GunlukEkraniTests(GunlukTemel):
    def setUp(self):
        self.yonetici = get_user_model().objects.create_superuser("yon", password="Guclu-Parola-9")
        self.sade = get_user_model().objects.create_user("sade", password="x", is_staff=True)
        with gunluk.kullanici_olarak("ali"):
            self.b = self.belge()
            self.b.tutar_kurus = 250000
            self.b.save()
        self.client.force_login(self.yonetici)

    def test_yetkiler(self):
        self.client.logout()
        r = self.client.get(reverse("gunluk_sayfasi"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])
        self.client.force_login(self.sade)
        self.assertEqual(self.client.get(reverse("gunluk_sayfasi")).status_code, 403)

    def test_icerik_ve_filtreler(self):
        r = self.client.get(reverse("gunluk_sayfasi"))
        self.assertContains(r, "1.000,00 ₺")
        self.assertContains(r, "2.500,00 ₺")
        self.assertContains(r, "ali")
        self.assertContains(self.client.get(reverse("gunluk_sayfasi"), {"islem": "DEGISTI"}), "2.500,00 ₺")
        self.assertNotContains(self.client.get(reverse("gunluk_sayfasi"), {"islem": "DEGISTI", "kullanici": "yok"}), "2.500,00")
        self.assertContains(self.client.get(reverse("gunluk_sayfasi"), {"model": "Belge", "nesne": self.b.pk}), "2.500,00 ₺")
        self.assertNotContains(self.client.get(reverse("gunluk_sayfasi"), {"model": "Belge", "nesne": self.b.pk + 999}), "2.500,00")
        self.assertContains(self.client.get(reverse("gunluk_sayfasi"), {"q": "Alış Fişi"}), "Alış Fişi")
        self.assertEqual(self.client.get(reverse("gunluk_sayfasi"), {"bas": "2000-01-01", "bit": "2999-01-01"}).status_code, 200)
        self.assertNotContains(self.client.get(reverse("gunluk_sayfasi"), {"bas": "2999-01-01"}), "2.500,00")
        for kotu in ({"bas": "abc"}, {"bit": "31.02.2026"}, {"sayfa": "999"}, {"islem": "x"}, {"nesne": "zz"}):
            self.assertEqual(self.client.get(reverse("gunluk_sayfasi"), kotu).status_code, 200, kotu)

    def test_html_kacisi(self):
        c = Cari.objects.create(unvan="<script>alert(1)</script>")
        r = self.client.get(reverse("gunluk_sayfasi"))
        self.assertContains(r, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(r, "<script>alert(1)</script>")

    def test_yonetim_paneli_salt_okunur_ve_gecmis_baglantisi(self):
        self.assertEqual(self.client.get(reverse("admin:defter_islemgunlugu_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:defter_islemgunlugu_add")).status_code, 403)
        g = IslemGunlugu.objects.first()
        self.assertEqual(self.client.post(reverse("admin:defter_islemgunlugu_change", args=[g.pk]), {}).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:defter_islemgunlugu_delete", args=[g.pk]), {"post": "yes"}).status_code, 403)
        r = self.client.get(reverse("admin:defter_belge_change", args=[self.b.pk]))
        self.assertContains(r, "Değişiklik geçmişi")
        self.assertContains(r, f"nesne={self.b.pk}")


class UpdateKorumaTesti(TestCase):
    """İzlenen modellerde toplu queryset.update() sinyal göndermez ve günlüğü atlar. Uygulama kodunda
    kullanılmamalı; zorunlu bir yer varsa açıkça gunluk.yaz() ile kaydedilmeli (şu an yalnızca eslestir)."""

    def test_update_kullanimi_yalniz_izin_verilen_yerde(self):
        desen = re.compile(r"\)\s*\.update\(|objects\.update\(")
        bulunan = []
        for p in sorted(BASE.glob("*.py")) + sorted((BASE / "management" / "commands").glob("*.py")):
            if p.name.startswith("test") or p.name == "tests.py":
                continue
            for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
                if desen.search(satir) and "attrs.update" not in satir:
                    bulunan.append((p.name, no))
        self.assertEqual([b[0] for b in bulunan], ["kasa_servisi.py"], bulunan)
        self.assertIn("gunluk.yaz", (BASE / "kasa_servisi.py").read_text(encoding="utf-8"))
