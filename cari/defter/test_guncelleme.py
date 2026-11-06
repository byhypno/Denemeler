import socket
import sqlite3
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from . import guncelleme as g
from . import yedek as yd

BASE = Path(__file__).resolve().parent.parent


class VeritabaniDoluMuTests(TestCase):
    def test_durumlar(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            def kontrol(yol):
                with mock.patch.dict(settings.DATABASES["default"], {"NAME": yol}):
                    return g.veritabani_dolu_mu()
            self.assertFalse(kontrol(d / "yok.sqlite3"))
            (d / "bos.sqlite3").write_bytes(b"")
            self.assertFalse(kontrol(d / "bos.sqlite3"))
            sqlite3.connect(d / "tablosuz.sqlite3").close()
            self.assertFalse(kontrol(d / "tablosuz.sqlite3"))
            con = sqlite3.connect(d / "dolu.sqlite3")
            con.execute("CREATE TABLE x (a)")
            con.commit()
            con.close()
            self.assertTrue(kontrol(d / "dolu.sqlite3"))

    def test_test_veritabani_guncel_bekleyen_yok(self):
        self.assertEqual(g.bekleyen_gecisler(), [])


class GuvenliMigrateTests(TestCase):
    def kur(self, plan=("a", "b"), dolu=True, dogrulama_ok=True):
        yamalar = {
            "plan": mock.patch.object(g, "bekleyen_gecisler", return_value=list(plan)),
            "dolu": mock.patch.object(g, "veritabani_dolu_mu", return_value=dolu),
            "olustur": mock.patch.object(g.yd, "yedek_olustur", return_value=Path("/yedek/cari_yedek_X.zip")),
            "dogrula": mock.patch.object(g.yd, "yedek_dogrula",
                                         return_value=yd.Dogrulama(ok=dogrulama_ok, hatalar=[] if dogrulama_ok else ["bozuk"])),
            "migrate": mock.patch.object(g, "call_command"),
        }
        m = {ad: p.start() for ad, p in yamalar.items()}
        for p in yamalar.values():
            self.addCleanup(p.stop)
        return m

    def test_bekleyen_yoksa_hicbir_sey_yapmaz(self):
        m = self.kur(plan=())
        self.assertEqual(g.guvenli_migrate(lambda *_: None), {"uygulanan": 0, "yedek": None})
        m["olustur"].assert_not_called()
        m["migrate"].assert_not_called()

    def test_dolu_veritabaninda_once_yedek_sonra_migrate(self):
        sira = []
        m = self.kur()
        m["olustur"].side_effect = lambda *a, **k: (sira.append("yedek"), Path("/y/z.zip"))[1]
        m["dogrula"].side_effect = lambda *a, **k: (sira.append("dogrula"), yd.Dogrulama())[1]
        m["migrate"].side_effect = lambda *a, **k: sira.append("migrate")
        s = g.guvenli_migrate(lambda *_: None)
        self.assertEqual(sira, ["yedek", "dogrula", "migrate"])
        self.assertEqual((s["uygulanan"], s["yedek"]), (2, Path("/y/z.zip")))

    def test_yedek_dogrulanamazsa_migrate_UYGULANMAZ(self):
        m = self.kur(dogrulama_ok=False)
        with self.assertRaises(yd.YedekHatasi):
            g.guvenli_migrate(lambda *_: None)
        m["migrate"].assert_not_called()

    def test_yedek_alinamazsa_migrate_UYGULANMAZ(self):
        m = self.kur()
        m["olustur"].side_effect = OSError("disk dolu")
        with self.assertRaises(OSError):
            g.guvenli_migrate(lambda *_: None)
        m["migrate"].assert_not_called()

    def test_yeni_kurulumda_yedek_yok(self):
        m = self.kur(dolu=False)
        g.guvenli_migrate(lambda *_: None)
        m["olustur"].assert_not_called()
        m["migrate"].assert_called_once()

    def test_yedek_hedefi_secimi(self):
        m = self.kur()
        with override_settings(YEDEK_DIZINLERI=[Path("/ayri/disk"), Path("/ikinci")]):
            g.guvenli_migrate(lambda *_: None)
        self.assertEqual(m["olustur"].call_args[0][0], Path("/ayri/disk"))
        m["olustur"].reset_mock()
        with override_settings(YEDEK_DIZINLERI=[], VERI_DIZINI=Path("/veri")):
            g.guvenli_migrate(lambda *_: None)
        self.assertEqual(m["olustur"].call_args[0][0], Path("/veri/otomatik_yedek"))


class SunucuKomutuTests(TestCase):
    def test_port_doluysa_ikinci_sunucu_acilmaz(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            with mock.patch("defter.management.commands.sunucu.guncelleme.guvenli_migrate") as gm, \
                    mock.patch("waitress.serve") as serve:
                out = StringIO()
                call_command("sunucu", port=port, tarayici_yok=True, stdout=out)
        finally:
            s.close()
        self.assertIn("zaten", out.getvalue())
        gm.assert_not_called()
        serve.assert_not_called()

    def test_yalniz_yerel_adreste_baslar(self):
        with mock.patch("waitress.serve") as serve, \
                mock.patch("defter.management.commands.sunucu.guncelleme.guvenli_migrate"):
            call_command("sunucu", port=59123, tarayici_yok=True, stdout=StringIO())
        self.assertEqual(serve.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(serve.call_args.kwargs["port"], 59123)

    def test_yedek_hatasinda_baslamaz(self):
        from django.core.management.base import CommandError
        with mock.patch("waitress.serve") as serve, \
                mock.patch("defter.management.commands.sunucu.guncelleme.guvenli_migrate",
                           side_effect=yd.YedekHatasi("yedek doğrulanamadı")):
            with self.assertRaises(CommandError):
                call_command("sunucu", port=59124, tarayici_yok=True, stdout=StringIO())
        serve.assert_not_called()


class WindowsBetikleriTests(TestCase):
    """Windows'ta denenemeyen betiklerin bozulmasına karşı asgari koruma."""

    BETIKLER = ["kur.bat", "baslat.bat", "yedek_al.bat", "yedek_gorevi_kur.bat", "ayarlar.ornek.bat"]

    def test_crlf_ve_ascii(self):
        for ad in self.BETIKLER:
            veri = (BASE / ad).read_bytes()
            self.assertTrue(veri.isascii(), f"{ad}: ASCII dışı karakter (kod sayfası sorunu çıkarır)")
            self.assertIn(b"\r\n", veri, ad)
            self.assertNotIn(b"\n", veri.replace(b"\r\n", b""), f"{ad}: LF-only satır sonu var")

    def test_onemli_satirlar(self):
        kur = (BASE / "kur.bat").read_text()
        for parca in ("venv", "requirements.txt", "veritabani_guncelle", "createsuperuser", "WScript.Shell"):
            self.assertIn(parca, kur)
        self.assertIn("manage.py sunucu", (BASE / "baslat.bat").read_text())
        self.assertIn("schtasks /create", (BASE / "yedek_gorevi_kur.bat").read_text())
        self.assertIn("yedek_al", (BASE / "yedek_al.bat").read_text())
        self.assertIn("CARI_YEDEK_DIZINLERI", (BASE / "ayarlar.ornek.bat").read_text())

    def test_gereksinimler(self):
        r = (BASE / "requirements.txt").read_text().lower()
        for paket in ("django", "openpyxl", "whitenoise", "waitress"):
            self.assertIn(paket, r)

    def test_yerel_ayar_dosyasi_depoya_girmez(self):
        gi = (BASE.parent / ".gitignore").read_text()
        self.assertIn("cari/ayarlar.bat", gi)
        self.assertIn("cari/veri/", gi)
        self.assertIn("*.bat text eol=crlf", (BASE.parent / ".gitattributes").read_text())
