"""Sunucu kaydı ve yeniden başlatma: sunucu beklenmedik durursa nedeni kayda geçer, baslat.bat yeniden dener."""
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase

BASE = Path(__file__).resolve().parent.parent


class SunucuKayitTests(SimpleTestCase):
    def calistir(self, serve_yan_etki=None):
        with mock.patch("defter.management.commands.sunucu.guncelleme.guvenli_migrate"), \
                mock.patch("django.core.wsgi.get_wsgi_application"), \
                mock.patch("waitress.serve", side_effect=serve_yan_etki) as serve, \
                mock.patch("defter.management.commands.sunucu.webbrowser.open"), \
                mock.patch("socket.socket.connect_ex", return_value=1):                       # port boş
            out = StringIO()
            call_command("sunucu", "--port", "8999", "--tarayici-yok", stdout=out)
        return out.getvalue(), serve

    def test_normal_kapanis_ve_baslangic_kayda_gecer(self):
        with self.assertLogs("defter.sunucu", "INFO") as k:
            out, serve = self.calistir()
        self.assertEqual(len(serve.call_args_list), 1)
        self.assertIn("127.0.0.1", serve.call_args.kwargs["host"])
        self.assertTrue(any("başlıyor" in m for m in k.output))
        self.assertTrue(any("normal kapandı" in m for m in k.output))
        self.assertIn("KAPATMAYIN", out)
        self.assertIn("sunucu.log", out)                           # kullanıcıya kayıt dosyasının yeri söylenir

    def test_ctrl_c_hata_sayilmaz(self):
        with self.assertLogs("defter.sunucu", "INFO") as k:
            self.calistir(KeyboardInterrupt())
        self.assertTrue(any("Ctrl+C" in m for m in k.output))

    def test_beklenmedik_durma_istisna_kayda_gecer_ve_yeniden_firlatilir(self):
        with self.assertLogs("defter.sunucu", "ERROR") as k:
            with self.assertRaises(RuntimeError):
                self.calistir(RuntimeError("test çökmesi"))
        self.assertTrue(any("BEKLENMEDİK" in m and "test çökmesi" in m for m in k.output))      # iz (traceback) de kayıtta


class KayitAyariTests(SimpleTestCase):
    def test_logging_dosya_ve_donus(self):
        d = settings.LOGGING["handlers"]["dosya"]
        self.assertTrue(d["filename"].endswith("sunucu.log"))
        self.assertEqual(d["backupCount"], 3)                       # dosya sonsuz büyümez
        self.assertLessEqual(d["maxBytes"], 2_000_000)
        self.assertIn("django.request", settings.LOGGING["loggers"])   # 500 hataları da kayda geçer

    def test_baslat_bat_yeniden_dener_ve_kayda_yonlendirir(self):
        b = (BASE / "baslat.bat").read_text()
        self.assertIn(":basla", b)
        self.assertIn("goto basla", b)
        self.assertIn("if %DENEME% GEQ 5 goto hata", b)             # sonsuz döngü yok
        self.assertIn("veri\\sunucu.log", b)
        self.assertIn("KAPATMAYIN", b)
