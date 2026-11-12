"""Cari hareketi (fiş) düzeltme: tür/cari sabit, KDV yeniden hesap, kalemler, çift giriş denetimi, günlük, yetki."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import Belge, BelgeKalem, Cari, IslemGunlugu
from .test_yardimci import rol_kullanici


class Temel(TestCase):
    def setUp(self):
        self.cari = Cari.objects.create(unvan="ÖRNEK A.Ş.")
        self.user = rol_kullanici("m", "Muhasebe")
        self.client.force_login(self.user)

    def belge(self, tur="ALIS_FISI", tutar=100000, **kw):
        kw.setdefault("tarih", date(2026, 3, 1))
        return Belge.objects.create(cari=self.cari, tur=tur, tutar_kurus=tutar, **kw)

    def veri(self, b, **kw):
        d = {"tur": b.tur, "tarih": b.tarih.isoformat(), "evrak_no": b.evrak_no, "harici_evrak_no": b.harici_evrak_no,
             "aciklama": b.aciklama, "odeme_sekli": b.odeme_sekli, "tutar_kurus": "1.000,00", "kdv_modu": "BILINMIYOR",
             "kdv_orani": "", "tevkifat_orani": "", "kalem_sayisi": "0"}
        d.update(kw)
        return d

    def url(self, b):
        return reverse("belge_duzelt", args=[b.pk])


class DuzeltTests(Temel):
    def test_alan_duzeltme_ve_tur_cari_sabit(self):
        b = self.belge(aciklama="eski")
        r = self.client.post(self.url(b), self.veri(b, aciklama="yeni", tutar_kurus="1.250,50", tarih="2026-03-05",
                                                    tur="ODEME"))              # tür değiştirmeye çalış
        self.assertEqual(r.status_code, 302)
        b.refresh_from_db()
        self.assertEqual((b.aciklama, b.tutar_kurus, b.tarih, b.tur, b.cari_id), ("yeni", 125050, date(2026, 3, 5), "ALIS_FISI", self.cari.pk))
        self.assertEqual(self.cari.bakiye_kurus(), 125050)

    def test_form_mevcut_degerlerle_dolu(self):
        b = self.belge(aciklama="X", evrak_no="12")
        r = self.client.get(self.url(b))
        self.assertContains(r, "Hareketi düzelt")
        self.assertContains(r, 'value="12"')
        self.assertContains(r, "1.000,00")
        self.assertNotContains(r, "Kaydet ve yenisini ekle")

    def test_kdv_yeniden_hesaplanir_cift_donusum_olmaz(self):
        b = self.belge(tutar=100000, kdv_modu="HARIC", kdv_orani=Decimal("20"))     # 1.000 matrah + KDV
        b.refresh_from_db()
        self.assertEqual(b.tutar_kurus, 120000)
        r = self.client.get(self.url(b))
        self.assertContains(r, "1.000,00")                                           # girilen tutar (matrah) gösterilir
        r = self.client.post(self.url(b), self.veri(b, tutar_kurus="1.000,00", kdv_modu="HARIC", kdv_orani="20"))
        self.assertEqual(r.status_code, 302)
        b.refresh_from_db()
        self.assertEqual((b.matrah_kurus, b.kdv_kurus, b.tutar_kurus), (100000, 20000, 120000))   # 144.000 olmadı

    def test_kdv_den_kdv_siz_e(self):
        b = self.belge(tutar=100000, kdv_modu="DAHIL", kdv_orani=Decimal("20"))
        r = self.client.post(self.url(b), self.veri(b, tutar_kurus="900,00"))
        self.assertEqual(r.status_code, 302)
        b.refresh_from_db()
        self.assertEqual((b.tutar_kurus, b.kdv_modu, b.matrah_kurus), (90000, "BILINMIYOR", None))

    def test_evrak_no_kendisiyle_cakismaz_digeriyle_cakisir(self):
        a, b = self.belge(evrak_no="1"), self.belge(evrak_no="2", tarih=date(2026, 3, 2))
        self.assertEqual(self.client.post(self.url(a), self.veri(a, aciklama="x")).status_code, 302)
        r = self.client.post(self.url(a), self.veri(a, evrak_no="2"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "zaten kayıtlı")
        a.refresh_from_db()
        self.assertEqual(a.evrak_no, "1")

    def test_cift_giris_uyarisi_kendisini_saymaz(self):
        a = self.belge(tutar=100000)
        r = self.client.post(self.url(a), self.veri(a, aciklama="yalnız açıklama"))      # aynı gün/tür/tutar: kendisi uyarı vermemeli
        self.assertEqual(r.status_code, 302)
        self.belge(tutar=50000)
        r = self.client.post(self.url(a), self.veri(a, tutar_kurus="500,00"))              # başka kayıtla aynı gün+tür+tutar
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "yine de kaydet")

    def test_iptal_edilmis_duzeltilemez(self):
        b = self.belge()
        Belge.objects.filter(pk=b.pk).update(iptal=True, iptal_nedeni="x")
        r = self.client.post(self.url(b), self.veri(b, aciklama="y"))
        self.assertEqual(r.status_code, 302)
        b.refresh_from_db()
        self.assertEqual(b.aciklama, "")

    def test_gunluge_eski_ve_yeni_yazilir(self):
        b = self.belge(aciklama="eski")
        self.client.post(self.url(b), self.veri(b, aciklama="yeni"))
        kayit = IslemGunlugu.objects.filter(model="Belge", islem="DEGISTI").latest("id")
        self.assertIn("eski", str(kayit.degisiklik))
        self.assertIn("yeni", str(kayit.degisiklik))

    def test_yetki(self):
        b = self.belge()
        self.client.logout()
        self.assertEqual(self.client.get(self.url(b)).status_code, 302)
        for rol in ("Görüntüleyici", "Kasiyer"):
            self.client.force_login(rol_kullanici("u" + rol[:3], rol))
            self.assertEqual(self.client.get(self.url(b)).status_code, 403, rol)
            self.assertEqual(self.client.post(self.url(b), self.veri(b, aciklama="z")).status_code, 403, rol)
        b.refresh_from_db()
        self.assertEqual(b.aciklama, "")

    def test_ekstrede_duzenle_baglantisi(self):
        b = self.belge()
        self.assertContains(self.client.get(reverse("cari_ekstre", args=[self.cari.pk])), self.url(b))
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        self.assertNotContains(self.client.get(reverse("cari_ekstre", args=[self.cari.pk])), self.url(b))


class KalemDuzeltTests(Temel):
    def kalemli(self):
        b = self.belge(tutar=300000)
        BelgeKalem.objects.create(belge=b, sira=1, aciklama="Vida", miktar=Decimal("10"), birim="ADET", birim_fiyat=Decimal("100"), tutar_kurus=100000)
        BelgeKalem.objects.create(belge=b, sira=2, aciklama="Somun", miktar=Decimal("2.5"), birim="KG", birim_fiyat=Decimal("800"), tutar_kurus=200000)
        return b

    def satir(self, i, ac, miktar, birim, fiyat, tutar):
        return {f"kalem_aciklama_{i}": ac, f"kalem_miktar_{i}": miktar, f"kalem_birim_{i}": birim, f"kalem_fiyat_{i}": fiyat, f"kalem_tutar_{i}": tutar}

    def test_mevcut_kalemler_forma_dolar(self):
        r = self.client.get(self.url(self.kalemli()))
        self.assertContains(r, 'value="Vida"')
        self.assertContains(r, 'value="2,5"')

    def test_kalemler_degismeden_kaydedilirse_dokunulmaz(self):
        b = self.kalemli()
        eski = list(b.kalemler.values_list("pk", flat=True))
        veri = self.veri(b, tutar_kurus="3.000,00", kalem_sayisi="2", aciklama="sadece not")
        veri.update(self.satir(0, "Vida", "10", "ADET", "100", "1.000,00"))
        veri.update(self.satir(1, "Somun", "2,5", "KG", "800", "2.000,00"))
        self.assertEqual(self.client.post(self.url(b), veri).status_code, 302)
        self.assertEqual(list(b.kalemler.values_list("pk", flat=True)), eski)       # aynı kayıtlar, yeniden yazılmadı

    def test_kalem_degisir_toplam_tutar_olur(self):
        b = self.kalemli()
        veri = self.veri(b, tutar_kurus="", kalem_sayisi="2")
        veri.update(self.satir(0, "Vida", "20", "ADET", "100", "2.000,00"))
        veri.update(self.satir(1, "Çivi", "1", "KG", "500,00", "999,00"))      # gönderilen tutar yok sayılır
        self.assertEqual(self.client.post(self.url(b), veri).status_code, 302)
        b.refresh_from_db()
        self.assertEqual(b.tutar_kurus, 250000)
        self.assertEqual(sorted(b.kalemler.values_list("aciklama", flat=True)), ["Vida", "Çivi"])
        self.assertEqual(b.kalemler.get(aciklama="Vida").miktar, Decimal("20"))

    def test_hatali_kalem_hicbir_seyi_degistirmez(self):
        b = self.kalemli()
        veri = self.veri(b, tutar_kurus="3.000,00", aciklama="değişmemeli", kalem_sayisi="1")
        veri.update(self.satir(0, "Vida", "abc", "ADET", "100", "1.000,00"))
        r = self.client.post(self.url(b), veri)
        self.assertEqual(r.status_code, 200)
        b.refresh_from_db()
        self.assertEqual((b.aciklama, b.kalemler.count()), ("", 2))

    def test_tum_kalemler_silinebilir(self):
        b = self.kalemli()
        veri = self.veri(b, tutar_kurus="3.000,00", kalem_sayisi="0")
        self.assertEqual(self.client.post(self.url(b), veri).status_code, 302)
        self.assertEqual(b.kalemler.count(), 0)

    def test_fiyatsiz_eski_kalem_forma_turetilmis_fiyatla_gelir(self):
        b = self.belge(tutar=30000)
        BelgeKalem.objects.create(belge=b, sira=1, aciklama="Eski kalem", miktar=Decimal("4"), birim="AD", birim_fiyat=None, tutar_kurus=30000)
        r = self.client.get(self.url(b))
        self.assertContains(r, 'value="75"')                       # 300,00 / 4
        self.assertContains(r, 'value="300,00"')

    def test_tutar_alani_salt_okunur_ve_sunucu_hesabi_gecerli(self):
        r = self.client.get(reverse("belge_yeni", args=[self.cari.pk]))
        self.assertContains(r, 'readonly tabindex="-1" class="kalem-tutar"')
        b = self.belge(tutar=100000)
        veri = self.veri(b, tutar_kurus="", kalem_sayisi="1")
        veri.update(self.satir(0, "Vida", "3", "AD", "0,335", "5000,00"))        # 3 × 0,335 = 1,005 -> 1,01
        self.assertEqual(self.client.post(self.url(b), veri).status_code, 302)
        b.refresh_from_db()
        self.assertEqual((b.kalemler.get().tutar_kurus, b.tutar_kurus), (101, 101))
