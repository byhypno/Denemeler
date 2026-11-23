"""Ödeme takvimi: vade grupları, FIFO ile açık tutar, ekran, yetki, panel uyarısı."""
from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import services
from .models import Belge, Cari
from .test_yardimci import rol_kullanici

BUGUN = date(2026, 6, 15)


class GrupTests(SimpleTestCase):
    def test_sinirlar(self):
        g = lambda gun: services.takvim_grubu(BUGUN + timedelta(days=gun), BUGUN)
        self.assertEqual(g(-1), "gecikmis")
        self.assertEqual((g(0), g(7)), ("hafta", "hafta"))      # bugün gecikmiş sayılmaz
        self.assertEqual((g(8), g(30)), ("ay", "ay"))
        self.assertEqual(g(31), "sonra")
        self.assertEqual(services.takvim_grubu(None, BUGUN), "vadesiz")


class TakvimServisTests(TestCase):
    def setUp(self):
        self.a = Cari.objects.create(unvan="A Ltd", vade_gun=30)
        self.b = Cari.objects.create(unvan="B Ltd")                    # vade tanımsız
        self.c = Cari.objects.create(unvan="C Ltd", vade_gun=10)

    def alis(self, cari, tarih, tutar, no=""):
        return Belge.objects.create(cari=cari, tur="ALIS_FISI", tarih=tarih, tutar_kurus=tutar, evrak_no=no)

    def grup(self, t, ad):
        return [g for g in t["gruplar"] if g["anahtar"] == ad][0]

    def test_gruplar_ve_toplamlar(self):
        self.alis(self.a, date(2026, 5, 1), 1000)      # vade 31.05 -> gecikmiş
        self.alis(self.a, date(2026, 5, 20), 2000)     # vade 19.06 -> hafta (4 gün)
        self.alis(self.c, date(2026, 6, 1), 500)       # vade 11.06 -> gecikmiş
        self.alis(self.a, date(2026, 6, 10), 4000)     # vade 10.07 -> 25 gün: ay
        self.alis(self.b, date(2026, 6, 1), 700)       # vadesiz
        t = services.odeme_takvimi(BUGUN)
        self.assertEqual(self.grup(t, "gecikmis")["toplam"], 1500)
        self.assertEqual(self.grup(t, "hafta")["toplam"], 2000)
        self.assertEqual(self.grup(t, "ay")["toplam"], 4000)
        self.assertEqual(self.grup(t, "vadesiz")["toplam"], 700)
        self.assertEqual(t["toplam"], 8200)
        self.assertEqual(t["vadesiz_cari_sayisi"], 1)

    def test_odeme_en_eski_borcu_kapatir_fifo(self):
        self.alis(self.a, date(2026, 5, 1), 1000)      # gecikmiş
        self.alis(self.a, date(2026, 5, 20), 2000)
        Belge.objects.create(cari=self.a, tur="ODEME", tarih=date(2026, 6, 1), tutar_kurus=1000)
        t = services.odeme_takvimi(BUGUN)
        self.assertEqual(self.grup(t, "gecikmis")["toplam"], 0)         # en eski kapandı
        self.assertEqual(self.grup(t, "hafta")["toplam"], 2000)

    def test_kismi_odeme_kalani_gosterir(self):
        self.alis(self.a, date(2026, 5, 1), 1000)
        Belge.objects.create(cari=self.a, tur="ODEME", tarih=date(2026, 6, 1), tutar_kurus=400)
        k = self.grup(services.odeme_takvimi(BUGUN), "gecikmis")["kalemler"][0]
        self.assertEqual(k["kalan_kurus"], 600)
        self.assertEqual(k["gun_kaldi"], (date(2026, 5, 31) - BUGUN).days)

    def test_iptal_belge_sayilmaz_ve_siralama_vadeye_gore(self):
        Belge.objects.create(cari=self.a, tur="ALIS_FISI", tarih=date(2026, 5, 1), tutar_kurus=9999, iptal=True, iptal_nedeni="x")
        self.alis(self.a, date(2026, 5, 10), 100, "2")   # vade 09.06
        self.alis(self.c, date(2026, 5, 1), 100, "1")    # vade 11.05 (daha eski vade)
        ks = self.grup(services.odeme_takvimi(BUGUN), "gecikmis")["kalemler"]
        self.assertEqual([k["belge"].evrak_no for k in ks], ["1", "2"])
        self.assertEqual(sum(k["kalan_kurus"] for k in ks), 200)

    def test_cari_filtresi_ve_avans(self):
        self.alis(self.a, date(2026, 5, 1), 1000)
        self.alis(self.c, date(2026, 5, 1), 500)
        t = services.odeme_takvimi(BUGUN, self.a)
        self.assertEqual(t["toplam"], 1000)
        Belge.objects.create(cari=self.b, tur="ODEME", tarih=date(2026, 6, 1), tutar_kurus=300)
        self.assertEqual(services.odeme_takvimi(BUGUN)["avans"], 300)

    def test_bos(self):
        t = services.odeme_takvimi(BUGUN)
        self.assertEqual((t["toplam"], t["vadesiz_cari_sayisi"]), (0, 0))


class TakvimEkranTests(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="Gecikmiş Tedarik", vade_gun=5)
        Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date.today() - timedelta(days=20), tutar_kurus=123450, evrak_no="9")
        self.url = reverse("odeme_takvimi")

    def test_sayfa_ve_dashboard_uyarisi(self):
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        for p in ("Vadesi geçmiş", "1.234,50", "15 gün gecikti", "Gecikmiş Tedarik", "Ödeme takvimi"):
            self.assertContains(r, p)
        d = self.client.get(reverse("dashboard"))
        self.assertContains(d, "Vadesi geçmiş")
        self.assertContains(d, "Ödeme takvimini aç")

    def test_vadesiz_uyarisi(self):
        Cari.objects.create(unvan="Vadesiz")
        Belge.objects.create(cari=Cari.objects.get(unvan="Vadesiz"), tur="ALIS_FISI", tarih=date.today(), tutar_kurus=100)
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        self.assertContains(self.client.get(self.url), "vade günü tanımlı değil")

    def test_yetki(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(rol_kullanici("k", "Kasiyer"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_bos_ve_cari_filtresi_cokmez(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        for q in ({"cari": "x"}, {"cari": "99999"}, {"cari": self.cari.pk}):
            self.assertEqual(self.client.get(self.url, q).status_code, 200, q)

    def test_html_kacar(self):
        c = Cari.objects.create(unvan="<script>z</script>", vade_gun=1)
        Belge.objects.create(cari=c, tur="ALIS_FISI", tarih=date.today() - timedelta(days=9), tutar_kurus=1)
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.assertNotContains(self.client.get(self.url), "<script>z</script>")
