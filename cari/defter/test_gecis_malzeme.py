"""Geçiş 0018: mevcut fiş kalemleri malzemelere gruplanır; kategoriler tahmin edilmez."""
import importlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MalzemeDoldurmaGecisiTests(TransactionTestCase):
    onceki = [("defter", "0016_genel_gider")]
    sonraki = [("defter", "0018_malzeme_doldur")]

    def migrate(self, hedef):
        ex = MigrationExecutor(connection)
        ex.migrate(hedef)
        return ex.loader.project_state(hedef).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def eski_veri(self, apps, adlar):
        Cari, Belge, Kalem = (apps.get_model("defter", m) for m in ("Cari", "Belge", "BelgeKalem"))
        c = Cari.objects.create(unvan="Geçiş Tedarik")
        b = Belge.objects.create(cari=c, tur="ALIS_FISI", tarih="2026-01-01", tutar_kurus=1000)
        for ad, birim in adlar:
            Kalem.objects.create(belge=b, aciklama=ad, birim=birim, tutar_kurus=100)

    def test_kalemler_gruplanir_kategoriler_hazir_gelir_tahmin_yok(self):
        apps = self.migrate(self.onceki)
        self.eski_veri(apps, (("Işık Kablosu", "metre"), ("ışık kablosu ", "metre"), ("ISIK KABLOSU", ""), ("Vida M8", "adet"), ("   ", "")))
        apps = self.migrate(self.sonraki)
        Kalem, Malzeme, Kat = (apps.get_model("defter", m) for m in ("BelgeKalem", "Malzeme", "MalzemeKategori"))
        self.assertEqual(Malzeme.objects.count(), 2)                                # 3 yazım tek malzeme + vida; boş açıklama atlanır
        kablo = Malzeme.objects.get(ad__icontains="kablosu")
        self.assertEqual(kablo.birim, "metre")
        self.assertEqual(Kalem.objects.filter(malzeme=kablo).count(), 3)
        self.assertEqual(Kalem.objects.filter(malzeme__isnull=True).count(), 1)     # yalnız boş açıklamalı kalem bağlanmadı
        self.assertEqual(Malzeme.objects.filter(kategori__isnull=False).count(), 0)  # kategori tahmini yok
        self.assertTrue(Kat.objects.filter(ad="Kaynak malzemeleri").exists())
        self.assertEqual(Kat.objects.get(ad="Diğer").sira, 900)

    def test_tekrar_calistirma_kopya_olusturmaz(self):
        apps = self.migrate(self.onceki)
        self.eski_veri(apps, (("Pense", ""),))
        apps = self.migrate(self.sonraki)
        importlib.import_module("defter.migrations.0018_malzeme_doldur").doldur(apps, None)
        self.assertEqual(apps.get_model("defter", "Malzeme").objects.count(), 1)
        self.assertEqual(apps.get_model("defter", "MalzemeKategori").objects.filter(ad="Diğer").count(), 1)
