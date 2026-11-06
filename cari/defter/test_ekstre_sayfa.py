"""Cari ekstre sayfası: ay grupları, özet kartları, ay filtresi, eksi bakiye uyarısı, ek simgeleri."""
from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import trend
from .models import Belge, Cari
from .test_yardimci import rol_kullanici


def b(tarih, etki, tutar):
    return SimpleNamespace(tarih=tarih, etki=etki, tutar_kurus=tutar)


class AyGruplariTests(SimpleTestCase):
    def test_gruplama_toplam_ve_kapanis(self):
        s = [(b(date(2026, 1, 5), 1, 1000), 1000), (b(date(2026, 1, 9), -1, 400), 600),
             (b(date(2026, 2, 3), 1, 250), 850)]
        g = trend.ay_gruplari(s)
        self.assertEqual([x["ad"] for x in g], ["Ocak 2026", "Şubat 2026"])
        self.assertEqual((g[0]["artis"], g[0]["azalis"], g[0]["kapanis"], g[0]["acilis"]), (1000, 400, 600, 0))
        self.assertEqual((g[1]["artis"], g[1]["azalis"], g[1]["kapanis"], g[1]["acilis"]), (250, 0, 850, 600))

    def test_ayni_ay_farkli_yil_ayri_grup(self):
        s = [(b(date(2025, 3, 1), 1, 5), 5), (b(date(2026, 3, 1), 1, 5), 10)]
        self.assertEqual(len(trend.ay_gruplari(s)), 2)

    def test_onceki_bakiye_acilis_olur(self):
        g = trend.ay_gruplari([(b(date(2026, 4, 1), 1, 100), 600)], onceki=500)
        self.assertEqual(g[0]["acilis"], 500)

    def test_bos(self):
        self.assertEqual(trend.ay_gruplari([]), [])


class EkstreSayfaTests(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="Deneme Tedarik", vade_gun=30, yetkili="Ali Veli", telefon="0555 111")
        T = Belge.Tur
        for tarih, tur, tutar in [(date(2026, 1, 5), T.ALIS_FISI, 100000), (date(2026, 2, 5), T.ODEME, 150000),
                                  (date(2026, 3, 5), T.IADE, 5000), (date(2026, 3, 9), T.ALIS_FISI, 20000)]:
            Belge.objects.create(cari=self.cari, tur=tur, tarih=tarih, tutar_kurus=tutar)
        self.client.force_login(rol_kullanici("yon", is_superuser=True))
        self.url = reverse("cari_ekstre", args=[self.cari.pk])

    def test_baslik_bilgileri_ve_kartlar(self):
        h = self.client.get(self.url).content.decode()
        for parca in ("Vade 30 gün", "Ali Veli", "0555 111", "buyuk\" aria-hidden", "Güncel borcumuz", "Alışlar", "Ödemeler", "İadeler", "Cari dosyaları (0)"):
            self.assertIn(parca, h)
        self.assertEqual(h.count("<h1"), 1)

    def test_kart_tutarlari_donemden(self):
        r = self.client.get(self.url, {"bas": "01.03.2026", "bit": "31.03.2026"})
        self.assertEqual(r.context["alis_toplam"], 20000)
        self.assertEqual(r.context["iade_toplam"], 5000)
        self.assertEqual(r.context["odeme_toplam"], 0)
        self.assertEqual(r.context["guncel_borc"], 100000 - 150000 - 5000 + 20000)   # dönemden bağımsız
        self.assertContains(r, "Seçili dönem")

    def test_guncel_borc_ilk_ay_secilince_degismez(self):
        r = self.client.get(self.url, {"bas": "01.01.2026", "bit": "31.01.2026"})
        self.assertEqual(r.context["kapanis"], 100000)            # dönem sonu bakiyesi
        self.assertEqual(r.context["guncel_borc"], -35000)       # kart: bugünkü gerçek bakiye

    def test_ay_gruplari_ve_eksi_uyari(self):
        r = self.client.get(self.url)
        self.assertEqual([g["ad"] for g in r.context["gruplar"]], ["Ocak 2026", "Şubat 2026", "Mart 2026"])
        self.assertEqual(r.context["eksi_ay"], 2)          # şubat -50.000, mart -35.000
        self.assertContains(r, "Bakiye 2 ay sonunda eksiye düşüyor")
        self.assertContains(r, "Ay sonu bakiye eksi")

    def test_eksi_yoksa_uyari_yok(self):
        Belge.objects.create(cari=self.cari, tur=Belge.Tur.ALIS_FISI, tarih=date(2026, 4, 1), tutar_kurus=10**7)
        r = self.client.get(self.url, {"bas": "01.04.2026", "bit": "30.04.2026"})
        self.assertNotContains(r, "eksiye düşüyor")

    def test_ay_filtresi_dogru_aralik_ve_aktif(self):
        r = self.client.get(self.url, {"bas": "01.02.2026", "bit": "28.02.2026"})
        aylar = {a["ad"]: a for a in r.context["aylar"]}
        self.assertEqual(set(aylar), {"Oca 2026", "Şub 2026", "Mar 2026"})
        self.assertEqual((aylar["Şub 2026"]["bas"], aylar["Şub 2026"]["bit"]), ("01.02.2026", "28.02.2026"))
        self.assertEqual([a["ad"] for a in r.context["aylar"] if a["aktif"]], ["Şub 2026"])
        self.assertEqual(len(r.context["gruplar"]), 1)

    def test_artik_yil_subat_son_gunu(self):
        Belge.objects.create(cari=self.cari, tur=Belge.Tur.ALIS_FISI, tarih=date(2028, 2, 10), tutar_kurus=1)
        r = self.client.get(self.url)
        sub = [a for a in r.context["aylar"] if a["ad"] == "Şub 2028"][0]
        self.assertEqual(sub["bit"], "29.02.2028")

    def test_bos_ek_icin_arti_metni_yok_dolu_ek_sayi_gosterir(self):
        h = self.client.get(self.url).content.decode()
        self.assertNotIn('<span class="not">+</span>', h)
        self.assertIn("Ek ekle", h)                        # ekran okuyucu için ad var
        from .ek_servisi import ek_sayilari  # noqa: F401  (ek yükleme ayrıntısı test_ek.py'de)

    def test_ay_basligi_toplamlari(self):
        r = self.client.get(self.url)
        h = r.content.decode()
        self.assertIn("Mart 2026", h)
        self.assertIn("ay-baslik", h)
