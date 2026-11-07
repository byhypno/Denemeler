"""baslangic_verisi komutu: ilk kurulumda Excel + fiş görselleri + cari dosyaları; mevcut veriye dokunmaz."""
import json
from datetime import date
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Belge, Cari, Ek

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class Temel(TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.kl = Path(self._t.name)

    def yaz(self, manifest, dosyalar=("cari.xlsx", "fis.zip", "ekstre.pdf")):
        for d in dosyalar:
            (self.kl / d).write_bytes(PDF if d.endswith(".pdf") else b"x")
        (self.kl / "yukle.json").write_text(json.dumps(manifest), encoding="utf-8")

    def calistir(self, **kw):
        out = StringIO()
        call_command("baslangic_verisi", "--klasor", str(self.kl), stdout=out, stderr=StringIO(), **kw)
        return out.getvalue()


class KomutTests(Temel):
    def test_klasor_veya_manifest_yoksa_sessizce_atlar(self):
        self.assertIn("atlandı", self.calistir())
        self.assertEqual(Cari.objects.count(), 0)

    def test_veri_varsa_hicbir_sey_yapmaz(self):
        self.yaz({"excel": "cari.xlsx"})
        Cari.objects.create(unvan="Mevcut")
        with mock.patch("defter.management.commands.baslangic_verisi.call_command") as cc:
            self.assertIn("YÜKLENMEDİ", self.calistir())
        cc.assert_not_called()

    def test_belge_varsa_da_atlar(self):
        self.yaz({"excel": "cari.xlsx"})
        c = Cari.objects.create(unvan="X")
        Belge.objects.create(cari=c, tur="ALIS_FISI", tarih=date(2026, 1, 1), tutar_kurus=100)
        with mock.patch("defter.management.commands.baslangic_verisi.call_command") as cc:
            self.calistir()
        cc.assert_not_called()

    def test_sira_excel_sonra_fis_gorselleri_sonra_cari_dosyasi(self):
        self.yaz({"excel": "cari.xlsx", "fis_gorselleri": [{"zip": "fis.zip", "cari": "ERÖZ HIRDAVAT"}],
                  "cari_dosyalari": [{"dosya": "ekstre.pdf", "cari": "ERÖZ HIRDAVAT", "aciklama": "ekstre"}]})
        cagrilar = []

        def sahte(ad, *a, **kw):
            cagrilar.append((ad, [Path(x).name if "/" in str(x) else x for x in a]))
            if ad == "excel_ice_aktar":
                Cari.objects.create(unvan="ERÖZ HIRDAVAT")

        with mock.patch("defter.management.commands.baslangic_verisi.call_command", side_effect=sahte):
            cikti = self.calistir()
        self.assertEqual(cagrilar, [("excel_ice_aktar", ["cari.xlsx"]), ("fis_gorselleri_ekle", ["fis.zip", "--cari", "ERÖZ HIRDAVAT"])])
        e = Ek.objects.get()                                              # cari dosyası (PDF) gerçekten eklendi
        self.assertEqual((e.orijinal_ad, e.aciklama, e.yukleyen), ("ekstre.pdf", "ekstre", "başlangıç verisi"))
        self.assertEqual(e.cari.unvan, "ERÖZ HIRDAVAT")
        self.assertIn("yüklendi", cikti)

    def test_tekrar_calisinca_cari_dosyasi_ikilenmez(self):
        Cari.objects.create(unvan="ERÖZ HIRDAVAT")
        # cari var -> komut zaten atlar; ek_ekle sha ile de korur
        from . import ek_servisi as es
        from django.core.files.uploadedfile import SimpleUploadedFile
        c = Cari.objects.get()
        es.ek_ekle(c, SimpleUploadedFile("a.pdf", PDF))
        with self.assertRaises(es.EkHatasi):
            es.ek_ekle(c, SimpleUploadedFile("b.pdf", PDF))

    def test_klasor_disina_cikan_yol_reddedilir(self):
        self.yaz({"excel": "../disari.xlsx"}, dosyalar=())
        (self.kl.parent / "disari.xlsx").write_bytes(b"x")
        self.addCleanup(lambda: (self.kl.parent / "disari.xlsx").unlink())
        with mock.patch("defter.management.commands.baslangic_verisi.call_command") as cc:
            with self.assertRaises(CommandError) as e:
                self.calistir()
        self.assertIn("klasör dışına", str(e.exception))
        cc.assert_not_called()

    def test_olmayan_dosya_ve_bozuk_manifest(self):
        self.yaz({"excel": "yok.xlsx"}, dosyalar=())
        with self.assertRaises(CommandError):
            self.calistir()
        (self.kl / "yukle.json").write_text("{bozuk", encoding="utf-8")
        with self.assertRaises(CommandError):
            self.calistir()

    def test_olmayan_cari_icin_cari_dosyasi_hata(self):
        self.yaz({"cari_dosyalari": [{"dosya": "ekstre.pdf", "cari": "Yok"}]})
        with self.assertRaises(CommandError):
            self.calistir()

    def test_kur_bat_komutu_cagirir(self):
        kur = (Path(__file__).resolve().parent.parent / "kur.bat").read_text()
        self.assertIn('if exist "baslangic_verisi\\yukle.json"', kur)
        self.assertIn("manage.py baslangic_verisi", kur)
