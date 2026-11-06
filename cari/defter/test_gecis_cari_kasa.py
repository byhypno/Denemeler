"""Geçiş 0015 (Cari Kasa kaldırma): veri kaybolmadan hesap/alanlar kaldırılır."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CariKasaKaldirmaGecisiTests(TransactionTestCase):
    onceki = [("defter", "0014_cari_kasa_on_yuzde_gizli")]
    sonraki = [("defter", "0015_cari_kasa_kaldir")]

    def migrate(self, hedef):
        ex = MigrationExecutor(connection)
        ex.migrate(hedef)
        return ex.loader.project_state(hedef).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_bos_cari_kasa_silinir_dolu_olan_pasif_kalir_ve_tedarikci_aciklamaya_yazilir(self):
        apps = self.migrate(self.onceki)
        Hesap, Hareket, Cari = (apps.get_model("defter", m) for m in ("Hesap", "KasaHareketi", "Cari"))
        ofis = Hesap.objects.get_or_create(ad="Ofis Kasa")[0]
        cari_kasa = Hesap.objects.get_or_create(ad="Cari Kasa", defaults={"cari_bagli": True})[0]
        cari = Cari.objects.create(unvan="Tedarik A")
        Hareket.objects.create(hesap=ofis, yon="GIRIS", tarih="2026-01-01", tutar_kurus=1000, aciklama="ofis")
        h = Hareket.objects.create(hesap=cari_kasa, yon="CIKIS", tarih="2026-01-02", tutar_kurus=2500,
                                   aciklama="havale", cari=cari)
        bos = Hesap.objects.create(ad="Bos Cari", cari_bagli=True)

        apps = self.migrate(self.sonraki)
        Hesap, Hareket = apps.get_model("defter", "Hesap"), apps.get_model("defter", "KasaHareketi")
        self.assertFalse(Hesap.objects.filter(ad="Bos Cari").exists())              # hareketsiz hesap silindi
        ck = Hesap.objects.get(ad="Cari Kasa")                                      # hareketli olan korundu
        self.assertFalse(ck.aktif)
        k = Hareket.objects.get(pk=h.pk)
        self.assertEqual((k.tutar_kurus, k.yon), (2500, "CIKIS"))                   # tutar kaybolmadı
        self.assertIn("Tedarik A", k.aciklama)                                       # düşen bilgi açıklamaya taşındı
        self.assertIn("havale", k.aciklama)
        self.assertEqual(Hareket.objects.get(hesap__ad="Ofis Kasa").aciklama, "ofis")  # ofis kasa etkilenmedi
        self.assertTrue(Hesap.objects.get(ad="Ofis Kasa").aktif)

    def test_hareketsiz_cari_kasa_silinir(self):
        apps = self.migrate(self.onceki)
        Hesap = apps.get_model("defter", "Hesap")
        Hesap.objects.get_or_create(ad="Ofis Kasa")[0]
        Hesap.objects.get_or_create(ad="Cari Kasa", defaults={"cari_bagli": True})[0]
        apps = self.migrate(self.sonraki)
        self.assertEqual(list(apps.get_model("defter", "Hesap").objects.values_list("ad", flat=True)), ["Ofis Kasa"])
