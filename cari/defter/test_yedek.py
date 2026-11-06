import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import yedek as yd
from .models import YedekKaydi

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 30


def sqlite_olustur(yol, cari=3, ek_yollari=(), wal=False):
    con = sqlite3.connect(yol)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    for t in ("defter_cari", "defter_belge", "defter_kasahareketi"):
        con.execute(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY, ad TEXT)")
    con.execute("CREATE TABLE defter_ek (id INTEGER PRIMARY KEY, yol TEXT)")
    for i in range(cari):
        con.execute("INSERT INTO defter_cari (ad) VALUES (?)", (f"cari{i}",))
    for y in ek_yollari:
        con.execute("INSERT INTO defter_ek (yol) VALUES (?)", (y,))
    con.commit()
    return con


class YedekTemel(TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.kok = Path(self._t.name)
        self.db = self.kok / "veri" / "cari.sqlite3"
        self.ekler = self.kok / "veri" / "ekler"
        self.db.parent.mkdir(parents=True)
        (self.ekler / "ab").mkdir(parents=True)
        (self.ekler / "ab" / "dosya1.png").write_bytes(PNG)
        (self.ekler / "ab" / ".gizli.tmp").write_bytes(b"yarim")            # geçici dosya yedeğe girmez
        sqlite_olustur(self.db, ek_yollari=["ab/dosya1.png"]).close()
        self.hedef = self.kok / "yedek"

    def yap(self, **kw):
        return yd.yedek_olustur(self.hedef, db_yolu=self.db, ek_dizini=self.ekler, **kw)

    def zip_yeniden_yaz(self, zip_yol, degistir):
        """Zip'i okuyup `degistir(uyeler:dict)` ile değiştirilmiş haliyle yeniden yazar."""
        with zipfile.ZipFile(zip_yol) as z:
            uyeler = {a: z.read(a) for a in z.namelist()}
        degistir(uyeler)
        with zipfile.ZipFile(zip_yol, "w") as z:
            for a, v in uyeler.items():
                z.writestr(a, v)


class YedekOlusturTests(YedekTemel):
    def test_icerik_manifest_ve_ozetler(self):
        z = self.yap(simdi=datetime(2026, 11, 6, 20, 15, 30))
        self.assertEqual(z.name, "cari_yedek_20261106_201530.zip")
        with zipfile.ZipFile(z) as zf:
            self.assertEqual(sorted(zf.namelist()), ["MANIFEST.json", "cari.sqlite3", "ekler/ab/dosya1.png"])
            m = json.loads(zf.read("MANIFEST.json"))
            self.assertEqual(m["sayilar"]["cari"], 3)
            self.assertEqual(m["sayilar"]["ek"], 1)
            self.assertEqual(m["dosyalar"]["ekler/ab/dosya1.png"]["sha256"], hashlib.sha256(PNG).hexdigest())
            self.assertEqual(m["dosyalar"]["cari.sqlite3"]["sha256"],
                             hashlib.sha256(zf.read("cari.sqlite3")).hexdigest())

    def test_gizli_anahtar_yedege_girmez(self):
        (self.db.parent / "secret.key").write_text("cok-gizli")
        with zipfile.ZipFile(self.yap()) as zf:
            self.assertFalse([a for a in zf.namelist() if "secret" in a])
            self.assertNotIn(b"cok-gizli", b"".join(zf.read(a) for a in zf.namelist()))

    def test_wal_modunda_yazilmamis_veri_de_yedege_girer(self):
        con = sqlite_olustur(self.db.with_name("wal.sqlite3"), cari=0, wal=True)
        con.execute("INSERT INTO defter_cari (ad) VALUES ('wal-kaydi')")
        con.commit()                                              # WAL'da; ana dosyaya henüz işlenmemiş olabilir
        try:
            z = yd.yedek_olustur(self.hedef, db_yolu=self.db.with_name("wal.sqlite3"), ek_dizini=self.ekler)
            with zipfile.ZipFile(z) as zf, tempfile.TemporaryDirectory() as t:
                zf.extract("cari.sqlite3", t)
                c = sqlite3.connect(Path(t) / "cari.sqlite3")
                self.assertEqual(c.execute("SELECT ad FROM defter_cari").fetchall(), [("wal-kaydi",)])
                c.close()
        finally:
            con.close()

    def test_gecici_dosya_kalmaz_ve_hata_halinde_yarim_yedek_olmaz(self):
        self.yap()
        self.assertEqual([p.name for p in self.hedef.iterdir() if p.name.startswith(".")], [])
        with mock.patch.object(yd, "_butunluk", return_value="database disk image is malformed"):
            with self.assertRaises(yd.YedekHatasi):
                self.yap(simdi=datetime(2030, 1, 1))
        self.assertEqual(len(list(self.hedef.iterdir())), 1)       # yalnızca ilk (geçerli) yedek

    def test_veritabani_yoksa_hata(self):
        with self.assertRaises(yd.YedekHatasi):
            yd.yedek_olustur(self.hedef, db_yolu=self.kok / "yok.sqlite3", ek_dizini=self.ekler)

    def test_ek_klasoru_yoksa_yine_de_yedeklenir(self):
        z = yd.yedek_olustur(self.hedef, db_yolu=self.db, ek_dizini=self.kok / "olmayan")
        with zipfile.ZipFile(z) as zf:
            self.assertEqual(sorted(zf.namelist()), ["MANIFEST.json", "cari.sqlite3"])


class DogrulamaTests(YedekTemel):
    def test_gecerli(self):
        d = yd.yedek_dogrula(self.yap())
        self.assertTrue(d.ok, d.hatalar)
        self.assertEqual((d.hatalar, d.uyarilar), ([], []))

    def test_bozulmus_uye(self):
        z = self.yap()
        self.zip_yeniden_yaz(z, lambda u: u.__setitem__("ekler/ab/dosya1.png", PNG + b"degisti"))
        d = yd.yedek_dogrula(z)
        self.assertFalse(d.ok)
        self.assertTrue(any("Özet tutmuyor" in h and "dosya1.png" in h for h in d.hatalar))

    def test_eksik_dosya_ve_fazla_dosya(self):
        z = self.yap()
        self.zip_yeniden_yaz(z, lambda u: (u.pop("ekler/ab/dosya1.png"), u.__setitem__("ekler/ekstra.png", PNG)))
        d = yd.yedek_dogrula(z)
        self.assertFalse(d.ok)
        self.assertTrue(any("Eksik dosya" in h for h in d.hatalar))
        self.assertTrue(any("ekstra.png" in u for u in d.uyarilar))

    def test_manifest_yok_veya_bozuk(self):
        z = self.yap()
        self.zip_yeniden_yaz(z, lambda u: u.pop("MANIFEST.json"))
        self.assertIn("MANIFEST.json yok.", yd.yedek_dogrula(z).hatalar)
        z2 = self.yap(simdi=datetime(2031, 1, 1))
        self.zip_yeniden_yaz(z2, lambda u: u.__setitem__("MANIFEST.json", b"{bozuk"))
        self.assertFalse(yd.yedek_dogrula(z2).ok)

    def test_zip_degil_veya_olmayan_dosya(self):
        rastgele = self.kok / "x.zip"
        rastgele.write_bytes(os.urandom(200))
        self.assertFalse(yd.yedek_dogrula(rastgele).ok)
        self.assertFalse(yd.yedek_dogrula(self.kok / "yok.zip").ok)

    def test_zip_slip_adlari_reddedilir(self):
        for kotu in ("../evil.txt", "/etc/passwd", "ekler/../../evil", "C:\\evil.txt", "\\\\sunucu\\x"):
            z = self.yap(simdi=datetime(2026, 1, 1, 0, 0, hash(kotu) % 60))
            self.zip_yeniden_yaz(z, lambda u, k=kotu: u.__setitem__(k, b"x"))
            d = yd.yedek_dogrula(z)
            self.assertFalse(d.ok, kotu)
            self.assertTrue(any("Güvensiz" in h for h in d.hatalar), kotu)

    def test_hash_tutan_ama_bozuk_sqlite_yakalanir(self):
        z = self.yap()
        cop = os.urandom(4096)
        def degistir(u):
            u["cari.sqlite3"] = cop
            m = json.loads(u["MANIFEST.json"])
            m["dosyalar"]["cari.sqlite3"] = {"sha256": hashlib.sha256(cop).hexdigest(), "boyut": len(cop)}
            u["MANIFEST.json"] = json.dumps(m).encode()
        self.zip_yeniden_yaz(z, degistir)
        d = yd.yedek_dogrula(z)
        self.assertFalse(d.ok)
        self.assertTrue(any("bütünlük" in h.lower() or "database" in h.lower() for h in d.hatalar), d.hatalar)


class GeriYuklemeTests(YedekTemel):
    def test_bos_klasore_geri_yukler(self):
        z = self.yap()
        hedef = self.kok / "yeni_veri"
        s = yd.geri_yukle(z, hedef)
        self.assertEqual(s["hedef"], hedef)
        self.assertEqual((hedef / "ekler" / "ab" / "dosya1.png").read_bytes(), PNG)
        c = sqlite3.connect(hedef / "cari.sqlite3")
        self.assertEqual(c.execute("SELECT COUNT(*) FROM defter_cari").fetchone()[0], 3)
        c.close()
        self.assertFalse((hedef / "MANIFEST.json").exists())

    def test_dolu_klasorun_ustune_yazmaz(self):
        z = self.yap()
        dolu = self.kok / "dolu"
        dolu.mkdir()
        (dolu / "onemli.txt").write_text("silinmemeli")
        with self.assertRaises(yd.YedekHatasi):
            yd.geri_yukle(z, dolu)
        self.assertEqual((dolu / "onemli.txt").read_text(), "silinmemeli")
        with self.assertRaises(yd.YedekHatasi):                       # çalışan veri klasörü de dolu
            yd.geri_yukle(z, self.db.parent)

    def test_gecersiz_yedek_geri_yuklenmez(self):
        z = self.yap()
        self.zip_yeniden_yaz(z, lambda u: u.__setitem__("ekler/ab/dosya1.png", b"bozuk"))
        hedef = self.kok / "yeni"
        with self.assertRaises(yd.YedekHatasi):
            yd.geri_yukle(z, hedef)
        self.assertFalse(hedef.exists())

    def test_zip_slip_dosya_olusturmaz(self):
        z = self.yap()
        self.zip_yeniden_yaz(z, lambda u: u.__setitem__("../kacak.txt", b"x"))
        with self.assertRaises(yd.YedekHatasi):
            yd.geri_yukle(z, self.kok / "yeni")
        self.assertFalse((self.kok / "kacak.txt").exists())

    def test_geri_yukleme_testi_gecer_ve_gecici_klasor_silinir(self):
        t = yd.geri_yukleme_testi(self.yap())
        self.assertTrue(t["ok"], t)
        self.assertEqual(t["sayilar"]["cari"], 3)

    def test_ek_kaydi_var_dosyasi_yoksa_yakalar(self):
        sqlite_olustur(self.db.with_name("b.sqlite3"), ek_yollari=["ab/dosya1.png", "ab/YOK.png"]).close()
        z = yd.yedek_olustur(self.hedef, db_yolu=self.db.with_name("b.sqlite3"), ek_dizini=self.ekler)
        t = yd.geri_yukleme_testi(z)
        self.assertFalse(t["ok"])
        self.assertTrue(any("YOK.png" in h for h in t["hatalar"]))


class SaklamaTests(TestCase):
    def test_kurallar(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            def yap(t):
                (d / f"cari_yedek_{t:%Y%m%d_%H%M%S}.zip").write_bytes(b"x")
            simdi = datetime(2026, 11, 6, 12, 0)
            tarihler = [datetime(2026, 11, 5, 22), datetime(2026, 10, 20, 22),            # son 30 gün: kalır
                        datetime(2026, 9, 10, 22), datetime(2026, 9, 25, 22),             # eylül: yalnızca 25'i
                        datetime(2026, 8, 1, 22), datetime(2025, 12, 15, 22),             # kalır (ay başına 1)
                        datetime(2025, 12, 1, 22),                                        # aynı ay, eski: silinir
                        datetime(2025, 9, 1, 22)]                                         # 12 aydan eski: silinir
            for t in tarihler:
                yap(t)
            (d / "notlar.txt").write_text("dokunma")
            (d / "cari_yedek_bozuk_ad.zip").write_text("dokunma")
            silinen = yd.yedek_temizle(d, gunluk=30, aylik=12, simdi=simdi)
            kalan = sorted(p.name for p in d.iterdir())
            self.assertEqual(sorted(p.name for p in silinen),
                             ["cari_yedek_20250901_220000.zip", "cari_yedek_20251201_220000.zip",
                              "cari_yedek_20260910_220000.zip"])
            self.assertIn("notlar.txt", kalan)
            self.assertIn("cari_yedek_bozuk_ad.zip", kalan)
            self.assertIn("cari_yedek_20260925_220000.zip", kalan)

    def test_en_yeni_yedek_asla_silinmez(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "cari_yedek_20200101_000000.zip").write_bytes(b"x")                  # çok eski ama tek yedek
            self.assertEqual(yd.yedek_temizle(d, simdi=datetime(2026, 11, 6)), [])
            self.assertEqual(len(list(d.iterdir())), 1)

    def test_olmayan_klasor(self):
        self.assertEqual(yd.yedek_temizle("/yok/boyle/klasor"), [])


class YedekleTests(YedekTemel):
    def yedekle(self, hedefler, **kw):
        return yd.yedekle(hedefler, db_yolu=self.db, ek_dizini=self.ekler, **kw)

    def test_iki_hedef_ayni_icerik_kayit_tutulur(self):
        a, b = self.kok / "A", self.kok / "B"
        with mock.patch.object(yd, "ayni_disk_mi", return_value=False):
            kayitlar = self.yedekle([a, b])
        self.assertEqual([k.durum for k in kayitlar], ["TAMAM", "TAMAM"])
        self.assertTrue(all(k.dogrulandi and k.geri_yukleme_testi for k in kayitlar))
        ad = kayitlar[0].dosya
        self.assertEqual((a / ad).read_bytes(), (b / ad).read_bytes())
        self.assertEqual(YedekKaydi.objects.count(), 2)

    def test_ayni_diskte_uyari(self):
        with mock.patch.object(yd, "ayni_disk_mi", return_value=True):
            k = self.yedekle([self.kok / "A"])[0]
        self.assertEqual(k.durum, "UYARI")
        self.assertIn("diskte", k.ayrinti)

    def test_bir_hedef_basarisiz_digeri_calisir(self):
        dosya = self.kok / "bu_bir_dosya"
        dosya.write_text("klasor degil")
        iyi = self.kok / "iyi"
        with mock.patch.object(yd, "ayni_disk_mi", return_value=False):
            kayitlar = self.yedekle([dosya, iyi])
        self.assertEqual([k.durum for k in kayitlar], ["HATA", "TAMAM"])
        self.assertTrue(list(iyi.glob("cari_yedek_*.zip")))

    def test_hedef_yoksa_hata(self):
        with override_settings(YEDEK_DIZINLERI=[]):
            with self.assertRaises(yd.YedekHatasi):
                yd.yedekle(db_yolu=self.db)

    def test_ayarlardaki_hedefler_kullanilir_ve_temizlik_calisir(self):
        a = self.kok / "A"
        a.mkdir()
        (a / "cari_yedek_20260301_000000.zip").write_bytes(b"x")     # mart: ayın son yedeği kalır
        (a / "cari_yedek_20260302_000000.zip").write_bytes(b"x")
        (a / "cari_yedek_20200101_000000.zip").write_bytes(b"x")     # 12 aydan eski: silinir
        with override_settings(YEDEK_DIZINLERI=[a]), mock.patch.object(yd, "ayni_disk_mi", return_value=False):
            k = yd.yedekle(db_yolu=self.db, ek_dizini=self.ekler, simdi=datetime(2026, 11, 6, 12))[0]
        self.assertEqual(k.durum, "TAMAM")
        self.assertIn("2 eski yedek", k.ayrinti)
        self.assertEqual(sorted(p.name for p in a.glob("cari_yedek_*.zip")),
                         ["cari_yedek_20260302_000000.zip", "cari_yedek_20261106_120000.zip"])

    def test_durum_uyarisi(self):
        self.assertTrue(yd.yedek_durumu()["uyari"])                              # hiç yedek yok
        k = YedekKaydi.objects.create(hedef="x", durum="HATA")
        self.assertTrue(yd.yedek_durumu()["uyari"])                              # yalnızca başarısız
        k = YedekKaydi.objects.create(hedef="x", durum="TAMAM")
        self.assertFalse(yd.yedek_durumu()["uyari"])
        YedekKaydi.objects.filter(pk=k.pk).update(zaman=timezone.now() - timedelta(days=3))
        d = yd.yedek_durumu()
        self.assertTrue(d["uyari"])
        self.assertEqual(d["gun"], 3)
        YedekKaydi.objects.filter(pk=k.pk).update(zaman=timezone.now() - timedelta(days=1))
        self.assertFalse(yd.yedek_durumu()["uyari"])


class YedekEkranVeKomutTests(YedekTemel):
    def setUp(self):
        super().setUp()
        self.yonetici = get_user_model().objects.create_superuser("y", password="Guclu-Parola-9")
        self.sade = get_user_model().objects.create_user("s", password="x", is_staff=True)
        p = mock.patch.object(yd, "_db_yolu", return_value=self.db)
        p.start()
        self.addCleanup(p.stop)
        a = override_settings(EK_DIZINI=self.ekler)
        a.enable()
        self.addCleanup(a.disable)

    def test_sayfa_yetkileri(self):
        for ad in ("yedek_sayfasi",):
            self.assertEqual(self.client.get(reverse(ad)).status_code, 302)       # giriş gerekli
        self.assertEqual(self.client.post(reverse("yedek_al")).status_code, 302)
        self.client.force_login(self.sade)
        self.assertEqual(self.client.get(reverse("yedek_sayfasi")).status_code, 403)
        self.assertEqual(self.client.post(reverse("yedek_al")).status_code, 403)
        self.assertEqual(YedekKaydi.objects.count(), 0)

    def test_hedef_yokken_yonerge(self):
        self.client.force_login(self.yonetici)
        with override_settings(YEDEK_DIZINLERI=[]):
            r = self.client.get(reverse("yedek_sayfasi"))
            self.assertContains(r, "Yedek hedefi tanımlı değil")
            self.assertContains(r, "CARI_YEDEK_DIZINLERI")
            r = self.client.post(reverse("yedek_al"), follow=True)
            self.assertContains(r, "Yedek hedefi tanımlı değil")

    def test_ekrandan_yedek_al(self):
        self.client.force_login(self.yonetici)
        with override_settings(YEDEK_DIZINLERI=[self.hedef]), mock.patch.object(yd, "ayni_disk_mi", return_value=False):
            r = self.client.post(reverse("yedek_al"), follow=True)
            self.assertContains(r, "geri yükleme testi geçti")
            self.assertEqual(YedekKaydi.objects.get().durum, "TAMAM")
            r = self.client.get(reverse("yedek_sayfasi"))
            self.assertContains(r, "Güncel")
            self.assertNotContains(r, "Henüz hiç yedek alınmadı")

    def test_ayni_disk_uyarisi_ekranda(self):
        self.client.force_login(self.yonetici)
        with override_settings(YEDEK_DIZINLERI=[self.hedef]):
            self.assertContains(self.client.get(reverse("yedek_sayfasi")), "verinin diskinde")

    def test_uyari_seridi_yalniz_yoneticiye_ve_yedek_alininca_kaybolur(self):
        self.client.force_login(self.yonetici)
        self.assertContains(self.client.get(reverse("dashboard")), "Henüz hiç yedek alınmadı")
        YedekKaydi.objects.create(hedef="x", durum="TAMAM")
        self.assertNotContains(self.client.get(reverse("dashboard")), "Henüz hiç yedek alınmadı")
        YedekKaydi.objects.all().delete()
        self.client.force_login(self.sade)
        self.assertNotContains(self.client.get(reverse("dashboard")), "yedek alınmadı")

    def test_komutlar(self):
        out, err = StringIO(), StringIO()
        with mock.patch.object(yd, "ayni_disk_mi", return_value=False):
            call_command("yedek_al", "--hedef", str(self.hedef), stdout=out, stderr=err)
        self.assertIn("Tamam", out.getvalue())
        zip_yol = next(self.hedef.glob("cari_yedek_*.zip"))
        out = StringIO()
        call_command("yedek_dogrula", str(zip_yol), "--geri-yukleme-testi", stdout=out)
        self.assertIn("Geri yükleme testi geçti", out.getvalue())
        yeni = self.kok / "geri"
        out = StringIO()
        call_command("yedek_geri_yukle", str(zip_yol), "--hedef", str(yeni), stdout=out)
        self.assertTrue((yeni / "cari.sqlite3").exists())
        with self.assertRaises(CommandError):                                   # dolu klasöre geri yükleme yok
            call_command("yedek_geri_yukle", str(zip_yol), "--hedef", str(yeni), stdout=StringIO())
        self.zip_yeniden_yaz(zip_yol, lambda u: u.__setitem__("ekler/ab/dosya1.png", b"bozuk"))
        with self.assertRaises(CommandError):
            call_command("yedek_dogrula", str(zip_yol), stdout=StringIO(), stderr=StringIO())
        with self.assertRaises(CommandError):
            call_command("yedek_al", "--hedef", str(self.kok / "bu_bir_dosya"), stdout=StringIO(), stderr=StringIO()) \
                if (self.kok / "bu_bir_dosya").write_text("x") else None
