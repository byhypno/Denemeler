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

    def test_elle_girilmis_tedarikci_yuklemeyi_engellemez(self):
        self.yaz({"excel": "cari.xlsx"})
        Cari.objects.create(unvan="Mevcut")
        with mock.patch("defter.management.commands.baslangic_verisi.call_command") as cc:
            self.assertNotIn("YÜKLENMEDİ", self.calistir())
        cc.assert_called_once()

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


class EkstreHareketleriTests(Temel):
    def veri(self, bakiye=450, **kw):
        (self.kl / "h.json").write_text(json.dumps({
            "cari": "ÖRNEK ISI YALITIM", "kaynak": "ekstre", "beklenen_bakiye_kurus": bakiye * 100,
            "satirlar": [
                {"tarih": "2026-01-02", "evrak_no": "7", "aciklama": "ÇİMENTO", "tur": "ALIS_FISI", "tutar_kurus": 100000, "odeme_sekli": ""},
                {"tarih": "2026-01-03", "evrak_no": "8", "aciklama": "KUM", "tur": "ALIS_FISI", "tutar_kurus": 50000, "odeme_sekli": ""},
                {"tarih": "2026-01-04", "evrak_no": "9", "aciklama": "HAVALE ÖDEMESİ", "tur": "ODEME", "tutar_kurus": 100000, "odeme_sekli": "HAVALE"},
                {"tarih": "2026-01-05", "evrak_no": "10", "aciklama": "TUĞLA İADE", "tur": "IADE", "tutar_kurus": 5000, "odeme_sekli": ""}]}), encoding="utf-8")
        (self.kl / "yukle.json").write_text(json.dumps({"hareketler": [{"dosya": "h.json"}], **kw}), encoding="utf-8")

    def test_yukler_ve_bakiye_eslesir(self):
        self.veri(bakiye=450)
        cikti = self.calistir()
        c = Cari.objects.get(unvan="ÖRNEK ISI YALITIM")
        self.assertEqual((c.belgeler.count(), c.bakiye_kurus()), (4, 45000))
        b = c.belgeler.get(harici_evrak_no="9")
        self.assertEqual((b.tur, b.odeme_sekli, b.evrak_no), ("ODEME", "HAVALE", ""))
        self.assertIn("EŞLEŞTİ", cikti)

    def test_bakiye_eslesmezse_hicbir_sey_kaydedilmez(self):
        self.veri(bakiye=451)
        with self.assertRaises(CommandError):
            self.calistir()
        self.assertEqual((Cari.objects.count(), Belge.objects.count()), (0, 0))

    def test_tekrar_calistirmak_cogaltmaz(self):
        self.veri(bakiye=450)
        self.calistir()
        cikti = self.calistir()
        self.assertEqual(Belge.objects.count(), 4)
        self.assertIn("zaten hareketi var", cikti)

    def test_baska_tedarikcinin_belgesi_varken_de_yuklenir(self):
        diger = Cari.objects.create(unvan="BASKA")
        Belge.objects.create(cari=diger, tur="ALIS_FISI", tarih=date(2026, 1, 1), tutar_kurus=100)
        self.veri(bakiye=450)
        self.calistir()
        self.assertEqual(Cari.objects.get(unvan="ÖRNEK ISI YALITIM").belgeler.count(), 4)
        self.assertEqual(diger.belgeler.count(), 1)

    def test_elle_acilmis_bos_cari_kullanilir(self):
        mevcut = Cari.objects.create(unvan="ÖRNEK ISI YALITIM")
        self.veri(bakiye=450)
        self.calistir()
        self.assertEqual(Cari.objects.filter(unvan="ÖRNEK ISI YALITIM").count(), 1)
        self.assertEqual(mevcut.belgeler.count(), 4)

    def test_cari_dosyasi_tekrarda_ikilenmez(self):
        self.yaz({"cari_dosyalari": [{"dosya": "ekstre.pdf", "cari": "X", "aciklama": "e"}]})
        Cari.objects.create(unvan="X")
        self.calistir()
        self.calistir()
        self.assertEqual(Ek.objects.count(), 1)
