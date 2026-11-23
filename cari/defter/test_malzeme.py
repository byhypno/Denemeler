"""Malzeme kataloğu: fiyat hafızası, zam tespiti, kategoriler, birleştirme, sayfalar."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from . import malzeme_servisi as ms
from .models import Belge, BelgeKalem, Cari, IslemGunlugu, Malzeme, MalzemeKategori
from .test_yardimci import rol_kullanici


class Temel(TestCase):
    def setUp(self):
        self.a = Cari.objects.create(unvan="A Ltd")
        self.b = Cari.objects.create(unvan="B Ltd")

    def alis(self, cari, tarih, *kalemler, iptal=False, no=""):
        """kalemler: (ad, miktar, tutar_kurus[, birim_fiyat])"""
        belge = Belge.objects.create(cari=cari, tur="ALIS_FISI", tarih=tarih, tutar_kurus=sum(k[2] for k in kalemler),
                                     evrak_no=no, iptal=iptal, iptal_nedeni="x" if iptal else "")
        sonuc = []
        for i, k in enumerate(kalemler, start=1):
            sonuc.append(BelgeKalem.objects.create(belge=belge, sira=i, aciklama=k[0], miktar=Decimal(str(k[1])), tutar_kurus=k[2],
                                                   birim_fiyat=Decimal(str(k[3])) if len(k) > 3 else None))
        return belge, sonuc


class FiyatTests(Temel):
    def test_birim_fiyat_tutar_bolu_miktar_ve_girilen(self):
        _, (k,) = self.alis(self.a, date(2026, 1, 1), ("Vida", 4, 1000))
        self.assertEqual(ms.birim_fiyat(k), Decimal("250.0000"))                       # 10,00 ₺ / 4 = 2,50 ₺ = 250 kuruş
        _, (k2,) = self.alis(self.a, date(2026, 1, 2), ("Pense", 3, 1000, "3.5"))
        self.assertEqual(ms.birim_fiyat(k2), Decimal("350.0000"))                      # girilen birim fiyat öncelikli (3,50 ₺)

    def test_kesirli_miktar_ve_yuvarlama(self):
        _, (k,) = self.alis(self.a, date(2026, 1, 1), ("Halat", "2.5", 1001))
        self.assertEqual(ms.birim_fiyat(k), Decimal("400.4000"))

    def test_degisim_esigi(self):
        D = Decimal
        self.assertEqual(ms._degisim(D(110), D(100)), {"yon": "yukari", "yuzde": D("10.0")})
        self.assertEqual(ms._degisim(D(90), D(100)), {"yon": "asagi", "yuzde": D("10.0")})
        self.assertEqual(ms._degisim(D("100.4"), D(100))["yon"], "yatay")              # yarım kuruştan az: değişim sayılmaz
        self.assertEqual(ms._degisim(D("100.5"), D(100))["yon"], "yukari")
        self.assertIsNone(ms._degisim(D(5), None))

    def test_gecmis_sirasi_tarihe_gore_iptal_haric(self):
        self.alis(self.a, date(2026, 3, 1), ("Vida", 1, 300))
        self.alis(self.a, date(2026, 1, 1), ("Vida", 1, 100))                           # sonradan girildi ama tarihi eski
        self.alis(self.a, date(2026, 2, 1), ("VİDA", 1, 999), iptal=True)               # iptal: sayılmaz
        m = Malzeme.objects.get()
        g = ms.fiyat_gecmisi(m)
        self.assertEqual([x["fiyat"] for x in g], [Decimal("100.0000"), Decimal("300.0000")])
        self.assertIsNone(g[0]["degisim"])
        self.assertEqual(g[1]["degisim"], {"yon": "yukari", "yuzde": Decimal("200.0")})

    def test_ozet_son_onceki_adet_min_max(self):
        self.alis(self.a, date(2026, 1, 1), ("Vida", 1, 100))
        self.alis(self.b, date(2026, 2, 1), ("Vida", 1, 150))
        self.alis(self.a, date(2026, 3, 1), ("Vida", 2, 240))                           # birim 120
        o = ms.ozet_tablo()[Malzeme.objects.get().pk]
        self.assertEqual((o["son"]["fiyat"], o["onceki"]["fiyat"], o["adet"]), (Decimal("120.0000"), Decimal("150.0000"), 3))
        self.assertEqual((o["en_dusuk"], o["en_yuksek"], o["toplam_kurus"]), (Decimal("100.0000"), Decimal("150.0000"), 490))
        self.assertEqual(o["degisim"]["yon"], "asagi")
        self.assertEqual(o["son"]["cari"], self.a)

    def test_tek_alis_onceki_yok(self):
        self.alis(self.a, date(2026, 1, 1), ("Vida", 1, 100))
        o = ms.ozet_tablo()[Malzeme.objects.get().pk]
        self.assertIsNone(o["onceki"])
        self.assertIsNone(o["degisim"])


class EslemeTests(Temel):
    def test_kalem_kataloga_kendiliginden_baglanir_turkce_duyarsiz(self):
        _, (k1,) = self.alis(self.a, date(2026, 1, 1), ("Işık Kablosu", 1, 100))
        _, (k2,) = self.alis(self.b, date(2026, 1, 2), ("ışık  kablosu", 1, 110))
        _, (k3,) = self.alis(self.b, date(2026, 1, 3), ("ISIK KABLOSU", 1, 120))
        self.assertEqual(Malzeme.objects.count(), 1)
        self.assertEqual({k1.malzeme_id, k2.malzeme_id, k3.malzeme_id}, {Malzeme.objects.get().pk})

    def test_farkli_ad_ayri_malzeme_ve_bosluk_toparlanir(self):
        m1, y1 = ms.malzeme_bul_veya_olustur("  Vida   M8  ", "adet")
        m2, y2 = ms.malzeme_bul_veya_olustur("Vida M10")
        self.assertEqual((m1.ad, m1.birim, y1, y2), ("Vida M8", "adet", True, True))
        self.assertNotEqual(m1.pk, m2.pk)
        self.assertEqual(ms.malzeme_bul_veya_olustur("vida m8")[0].pk, m1.pk)

    def test_birlestir_tasir_pasif_yapar_ve_eski_ad_hedefe_gider(self):
        _, (k1,) = self.alis(self.a, date(2026, 1, 1), ("Elektrod", 1, 100))
        _, (k2,) = self.alis(self.a, date(2026, 2, 1), ("Oerlikon Elektrod", 1, 120))
        e, o = Malzeme.objects.get(ad="Elektrod"), Malzeme.objects.get(ad="Oerlikon Elektrod")
        ms.birlestir(e, o)
        e.refresh_from_db(); k1.refresh_from_db()
        self.assertEqual((e.aktif, e.birlestirildi), (False, o))
        self.assertEqual(k1.malzeme, o)
        self.assertEqual(len(ms.fiyat_gecmisi(o)), 2)
        _, (k3,) = self.alis(self.a, date(2026, 3, 1), ("elektrod", 1, 130))          # eski ad hâlâ yazılırsa hedefe gider
        self.assertEqual(k3.malzeme, o)
        self.assertEqual(Malzeme.objects.count(), 2)

    def test_birlestirme_zinciri_kisalir_ve_kendiyle_olmaz(self):
        a, b, c = (Malzeme.objects.create(ad=x) for x in ("a", "b", "c"))
        ms.birlestir(a, b)
        ms.birlestir(b, c)
        a.refresh_from_db()
        self.assertEqual(a.birlestirildi, c)
        with self.assertRaises(ValueError):
            ms.birlestir(c, c)

    def test_birlestirme_gunluge_yazilir(self):
        a, b = Malzeme.objects.create(ad="x"), Malzeme.objects.create(ad="y")
        ms.birlestir(a, b)
        self.assertTrue(IslemGunlugu.objects.filter(model="Malzeme", islem="DEGISTI").exists())


class ZamTests(Temel):
    def test_zam_azalis_esit_ve_ilk_alis(self):
        _, (k1,) = self.alis(self.a, date(2026, 1, 1), ("Vida", 1, 100))
        self.assertEqual(ms.zam_uyarilari([k1]), [])                                    # ilk alış: kıyas yok
        _, (k2,) = self.alis(self.a, date(2026, 2, 1), ("Vida", 1, 125))
        u = ms.zam_uyarilari([k2])
        self.assertEqual(len(u), 1)
        self.assertEqual((u[0]["onceki"], u[0]["yeni"], u[0]["yuzde"]), (Decimal("100.0000"), Decimal("125.0000"), Decimal("25.0")))
        self.assertEqual((u[0]["onceki_cari"], u[0]["onceki_tarih"]), (self.a, date(2026, 1, 1)))
        _, (k3,) = self.alis(self.b, date(2026, 3, 1), ("Vida", 1, 125))
        self.assertEqual(ms.zam_uyarilari([k3]), [])                                    # aynı fiyat
        _, (k4,) = self.alis(self.b, date(2026, 4, 1), ("Vida", 1, 90))
        self.assertEqual(ms.zam_uyarilari([k4]), [])                                    # indirim

    def test_geriye_donuk_giris_kendinden_onceki_alisla_kiyaslanir(self):
        self.alis(self.a, date(2026, 1, 1), ("Vida", 1, 100))
        self.alis(self.a, date(2026, 6, 1), ("Vida", 1, 500))
        _, (k,) = self.alis(self.a, date(2026, 3, 1), ("Vida", 1, 150))                 # ara tarihe sonradan girildi
        u = ms.zam_uyarilari([k])
        self.assertEqual((u[0]["onceki"], u[0]["yeni"]), (Decimal("100.0000"), Decimal("150.0000")))

    def test_hafiza_verisi(self):
        self.alis(self.a, date(2026, 1, 1), ("Vida", 2, 500))
        Malzeme.objects.create(ad="Yeni malzeme")
        pasif = Malzeme.objects.create(ad="Pasif", aktif=False)
        v = {x["ad"]: x for x in ms.hafiza_verisi()}
        self.assertEqual((v["Vida"]["fiyat"], v["Vida"]["tarih"], v["Vida"]["cari"]), ("2.5000", "01.01.2026", "A Ltd"))
        self.assertNotIn("fiyat", v["Yeni malzeme"])
        self.assertNotIn(pasif.ad, v)


class FisFormuTests(Temel):
    def setUp(self):
        super().setUp()
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.url = reverse("belge_yeni", args=[self.a.pk])

    def post(self, ad, tutar, miktar="1", fiyat="", tarih="2026-03-05", no="", **kw):
        d = {"tur": "ALIS_FISI", "tarih": tarih, "tutar_kurus": "", "kdv_modu": "BILINMIYOR", "evrak_no": no, "kalem_sayisi": "1",
             "kalem_aciklama_0": ad, "kalem_miktar_0": miktar, "kalem_birim_0": "adet", "kalem_fiyat_0": fiyat or tutar, "kalem_tutar_0": tutar}
        d.update(kw)
        return self.client.post(self.url, d, follow=True)

    def test_kalem_malzemeye_baglanir_ve_ikinci_giris_ayni_malzemeyi_kullanir(self):
        self.post("Kaynak pensesi", "225,00", no="1")
        self.post("kaynak PENSESİ", "240,00", tarih="2026-04-05", no="2")
        self.assertEqual(Malzeme.objects.count(), 1)
        self.assertEqual(Malzeme.objects.get().birim, "adet")
        self.assertEqual(BelgeKalem.objects.filter(malzeme=Malzeme.objects.get()).count(), 2)

    def test_zam_mesaji_yalniz_zamda_ve_ilkte_yok(self):
        r = self.post("Pense", "100,00", no="1")
        self.assertNotContains(r, "Zam:")
        r = self.post("Pense", "125,00", tarih="2026-04-05", no="2")
        self.assertContains(r, "Zam: Pense")
        self.assertContains(r, "100,00 ₺ → 125,00 ₺")
        self.assertContains(r, "%25,0 arttı")
        self.assertContains(r, "05.03.2026")                                            # önceki alışın tarihi
        r = self.post("Pense", "120,00", tarih="2026-05-05", no="3")
        self.assertNotContains(r, "Zam:")

    def test_birim_fiyat_tutar_miktardan_karsilastirilir(self):
        self.post("Halat", "", miktar="10", fiyat="5,00", no="1")                        # birim 5,00
        r = self.post("Halat", "", miktar="10", fiyat="6,00", tarih="2026-04-05", no="2")
        self.assertContains(r, "5,00 ₺ → 6,00 ₺")
        self.assertContains(r, "%20,0 arttı")

    def test_formda_hafiza_ve_liste(self):
        self.post("Vida", "50,00", no="1")
        r = self.client.get(self.url)
        self.assertContains(r, 'list="malzeme-listesi"')
        self.assertContains(r, '<option value="Vida">')
        self.assertContains(r, 'id="malzeme-hafiza"')
        self.assertContains(r, "malzeme adı")

    def test_yonetim_panelinden_girilen_kalem_de_kataloga_baglanir(self):
        belge, _ = self.alis(self.a, date(2026, 1, 1), ("Boya", 1, 100))
        k = BelgeKalem.objects.create(belge=belge, sira=2, aciklama="BOYA", tutar_kurus=200)
        self.assertEqual(k.malzeme, Malzeme.objects.get(ad="Boya"))


class SayfaTests(Temel):
    def setUp(self):
        super().setUp()
        self.kat = MalzemeKategori.objects.get(ad="El aletleri")
        self.bugun = date.today()
        self.alis(self.a, self.bugun - timedelta(days=60), ("Pense", 1, 10000), ("Kaynak teli", 1, 5000))
        self.alis(self.b, self.bugun - timedelta(days=10), ("Pense", 1, 12500), ("Kaynak teli", 1, 4000))      # pense ZAM, tel indirim
        self.alis(self.a, self.bugun - timedelta(days=400), ("Eski vida", 1, 100))
        self.alis(self.a, self.bugun - timedelta(days=300), ("Eski vida", 1, 150))                              # eski zam: pencere dışı
        self.pense = Malzeme.objects.get(ad="Pense")
        self.pense.kategori = self.kat
        self.pense.save()
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.url = reverse("malzemeler")

    def adlar(self, r):
        return [x["m"].ad for x in r.context["satirlar"]]

    def test_liste_ve_kartlar(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.adlar(r), ["Eski vida", "Kaynak teli", "Pense"])
        self.assertEqual((r.context["toplam"], r.context["kategorisiz"], r.context["zam_sayisi"]), (3, 2, 1))
        for p in ("125,00 ₺", "Son zamlar", "%25,0", "El aletleri"):
            self.assertContains(r, p)
        self.assertEqual(r.content.decode().count("<h1"), 1)

    def test_suzgecler(self):
        self.assertEqual(self.adlar(self.client.get(self.url, {"zam": "1"})), ["Eski vida", "Pense"])
        self.assertEqual(self.adlar(self.client.get(self.url, {"kategori": "yok"})), ["Eski vida", "Kaynak teli"])
        self.assertEqual(self.adlar(self.client.get(self.url, {"kategori": self.kat.pk})), ["Pense"])
        self.assertEqual(self.adlar(self.client.get(self.url, {"q": "KAYNAK"})), ["Kaynak teli"])
        self.assertEqual(self.adlar(self.client.get(self.url, {"q": "el aletleri"})), ["Pense"])             # kategori adına göre de arar
        self.assertEqual(self.adlar(self.client.get(self.url, {"sira": "zam", "zam": "1"})), ["Eski vida", "Pense"])   # %50 > %25
        for q in ({"kategori": "x"}, {"sira": "saçma"}, {"zam": "evet"}):
            self.assertEqual(self.client.get(self.url, q).status_code, 200, q)

    def test_pasif_varsayilan_gizli(self):
        Malzeme.objects.create(ad="Pasif malzeme", aktif=False)
        self.assertNotIn("Pasif malzeme", self.adlar(self.client.get(self.url)))
        self.assertIn("Pasif malzeme", self.adlar(self.client.get(self.url, {"pasif": "1"})))

    def test_toplu_kategori_kaydet(self):
        tel = Malzeme.objects.get(ad="Kaynak teli")
        k2 = MalzemeKategori.objects.get(ad="Kaynak malzemeleri")
        r = self.client.post(self.url, {"eylem": "kategori_kaydet", "idler": [tel.pk, self.pense.pk],
                                        f"kategori_{tel.pk}": k2.pk, f"kategori_{self.pense.pk}": ""}, follow=True)
        self.assertContains(r, "2 malzemenin kategorisi güncellendi")
        tel.refresh_from_db(); self.pense.refresh_from_db()
        self.assertEqual((tel.kategori, self.pense.kategori), (k2, None))
        r = self.client.post(self.url, {"eylem": "kategori_kaydet", "idler": [tel.pk], f"kategori_{tel.pk}": k2.pk}, follow=True)
        self.assertContains(r, "Değişiklik yok")                                      # değişmeyene dokunulmaz

    def test_bilinmeyen_kategori_idsi_kategorisiz_yapar(self):
        self.client.post(self.url, {"eylem": "kategori_kaydet", "idler": [self.pense.pk], f"kategori_{self.pense.pk}": "99999"})
        self.pense.refresh_from_db()
        self.assertIsNone(self.pense.kategori)

    def test_kategori_ekle_ve_tekrar_turkce_duyarsiz_reddedilir(self):
        self.client.post(self.url, {"eylem": "kategori_ekle", "ad": "  Kesici   uçlar "})
        self.assertTrue(MalzemeKategori.objects.filter(ad="Kesici uçlar").exists())
        n = MalzemeKategori.objects.count()
        for ad in ("KESİCİ UÇLAR", "kesici ucular".replace("ucular", "uçlar"), "el ALETLERİ", "  ", "x" * 81):
            self.client.post(self.url, {"eylem": "kategori_ekle", "ad": ad})
        self.assertEqual(MalzemeKategori.objects.count(), n)

    def test_detay(self):
        r = self.client.get(reverse("malzeme_detay", args=[self.pense.pk]))
        self.assertEqual(r.status_code, 200)
        for p in ("Pense", "125,00 ₺", "100,00 ₺", "Önceki alış fiyatı", "Tedarikçi karşılaştırması", "En ucuz", "%25,0", "g-malzeme"):
            self.assertContains(r, p)
        t = r.context["tedarikciler"]
        self.assertEqual([x["cari"] for x in t], [self.a, self.b])
        self.assertEqual(t[1]["ucuza_gore"], Decimal("25.0"))
        self.assertEqual([x["fiyat"] for x in r.context["gecmis"]], [Decimal("12500.0000"), Decimal("10000.0000")])   # en yeni üstte

    def test_detay_duzenle_ve_ad_cakismasi(self):
        url = reverse("malzeme_detay", args=[self.pense.pk])
        self.client.post(url, {"eylem": "duzenle", "ad": "Kaynak pensesi", "kategori": "", "birim": "adet", "aktif": "on"})
        self.pense.refresh_from_db()
        self.assertEqual((self.pense.ad, self.pense.kategori, self.pense.birim), ("Kaynak pensesi", None, "adet"))
        r = self.client.post(url, {"eylem": "duzenle", "ad": "KAYNAK TELİ", "aktif": "on"}, follow=True)
        self.assertContains(r, "ikisini birleştirmek")
        self.pense.refresh_from_db()
        self.assertEqual(self.pense.ad, "Kaynak pensesi")
        self.client.post(url, {"eylem": "duzenle", "ad": "Kaynak pensesi"})                            # aktif işareti yok -> pasif
        self.pense.refresh_from_db()
        self.assertFalse(self.pense.aktif)

    def test_detay_birlestir(self):
        tel = Malzeme.objects.get(ad="Kaynak teli")
        r = self.client.post(reverse("malzeme_detay", args=[tel.pk]), {"eylem": "birlestir", "hedef": self.pense.pk}, follow=True)
        self.assertRedirects(r, reverse("malzeme_detay", args=[self.pense.pk]))
        tel.refresh_from_db()
        self.assertEqual((tel.aktif, tel.birlestirildi), (False, self.pense))
        self.assertEqual(len(ms.fiyat_gecmisi(self.pense)), 4)
        for hedef in ("", "x", str(tel.pk)):
            r = self.client.post(reverse("malzeme_detay", args=[self.pense.pk]), {"eylem": "birlestir", "hedef": hedef}, follow=True)
            self.assertContains(r, "Birleştirilecek malzemeyi seçin")

    def test_olmayan_malzeme_404(self):
        self.assertEqual(self.client.get(reverse("malzeme_detay", args=[99999])).status_code, 404)

    def test_alissiz_malzeme_detayi_cokmez(self):
        m = Malzeme.objects.create(ad="Hiç alınmadı")
        r = self.client.get(reverse("malzeme_detay", args=[m.pk]))
        self.assertContains(r, "Henüz alış kaydı yok")

    def test_html_kacar(self):
        Malzeme.objects.create(ad="<script>m</script>")
        self.assertNotContains(self.client.get(self.url), "<script>m</script>")
        self.assertNotContains(self.client.get(reverse("malzeme_detay", args=[Malzeme.objects.get(ad="<script>m</script>").pk])), "<script>m</script>")


class YetkiTests(Temel):
    def setUp(self):
        super().setUp()
        self.alis(self.a, date(2026, 1, 1), ("Pense", 1, 100))
        self.m = Malzeme.objects.get()

    def test_goruntuleyici_gorur_yazamaz(self):
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        r = self.client.get(reverse("malzemeler"))
        self.assertEqual(r.status_code, 200)
        for yok in ("Kategorileri kaydet", "Yeni kategori", "<select name=\"kategori_"):
            self.assertNotContains(r, yok)
        d = self.client.get(reverse("malzeme_detay", args=[self.m.pk]))
        self.assertNotContains(d, "Malzemeyi düzenle")
        for url, veri in ((reverse("malzemeler"), {"eylem": "kategori_ekle", "ad": "X"}),
                          (reverse("malzeme_detay", args=[self.m.pk]), {"eylem": "duzenle", "ad": "Y"})):
            self.assertEqual(self.client.post(url, veri).status_code, 403)
        self.m.refresh_from_db()
        self.assertEqual(self.m.ad, "Pense")

    def test_kasiyer_ve_anonim(self):
        self.assertEqual(self.client.get(reverse("malzemeler")).status_code, 302)
        self.client.force_login(rol_kullanici("k", "Kasiyer"))
        self.assertEqual(self.client.get(reverse("malzemeler")).status_code, 403)
        self.assertEqual(self.client.get(reverse("malzeme_detay", args=[self.m.pk])).status_code, 403)

    def test_menu(self):
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.assertContains(self.client.get(reverse("dashboard")), reverse("malzemeler"))


class TopluAtamaTests(Temel):
    def setUp(self):
        super().setUp()
        for ad in ("A1", "A2", "A3"):
            self.alis(self.a, date(2026, 1, 1), (ad, 1, 100))
        self.ids = list(Malzeme.objects.order_by("ad").values_list("pk", flat=True))
        self.kat = MalzemeKategori.objects.get(ad="Sarf malzeme")
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        self.url = reverse("malzemeler")

    def test_secilenlere_kategori_atanir(self):
        r = self.client.post(self.url, {"eylem": "toplu_ata", "kategori_toplu": self.kat.pk, "sec": self.ids[:2]}, follow=True)
        self.assertContains(r, "2 malzeme")
        self.assertEqual(list(Malzeme.objects.filter(kategori=self.kat).values_list("pk", flat=True).order_by("pk")), self.ids[:2])

    def test_bos_secim_ve_gecersiz_kategori_reddedilir(self):
        r = self.client.post(self.url, {"eylem": "toplu_ata", "kategori_toplu": self.kat.pk}, follow=True)
        self.assertContains(r, "Önce listeden malzeme seçin")
        r = self.client.post(self.url, {"eylem": "toplu_ata", "kategori_toplu": "99999", "sec": self.ids}, follow=True)
        self.assertContains(r, "Kategoriyi seçin")
        self.assertEqual(Malzeme.objects.filter(kategori__isnull=False).count(), 0)

    def test_kategorisiz_yapma_ve_degismeyene_dokunmama(self):
        self.client.post(self.url, {"eylem": "toplu_ata", "kategori_toplu": self.kat.pk, "sec": self.ids})
        r = self.client.post(self.url, {"eylem": "toplu_ata", "kategori_toplu": self.kat.pk, "sec": self.ids}, follow=True)
        self.assertContains(r, "Değişiklik yok")
        self.client.post(self.url, {"eylem": "toplu_ata", "kategori_toplu": "", "sec": self.ids[:1]})
        self.assertEqual(Malzeme.objects.filter(kategori__isnull=True).count(), 1)

    def test_secim_kutulari_yalniz_yazana(self):
        self.assertContains(self.client.get(self.url), 'name="sec"')
        self.client.force_login(rol_kullanici("g", "Görüntüleyici"))
        self.assertNotContains(self.client.get(self.url), 'name="sec"')
        self.assertEqual(self.client.post(self.url, {"eylem": "toplu_ata", "sec": self.ids}).status_code, 403)
