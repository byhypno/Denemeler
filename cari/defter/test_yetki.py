import tempfile
from datetime import date
from io import StringIO

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from . import ek_servisi as es
from . import yetki
from .models import Belge, Cari, EkstreMutabakat, Hesap, IslemGunlugu, KasaHareketi
from .roller import MUHASEBE_OKUR, MUHASEBE_YAZAR, rolleri_kur
from .test_yardimci import rol_kullanici

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 30
GIRIS, CIKIS = "GIRIS", "CIKIS"
ROLLER = ("yonetici", "muhasebe", "goruntuleyici", "kasiyer", "rolsuz")
ONBELLEK = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "yetki-testi"}}


class YetkiTemel(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        a = override_settings(EK_DIZINI=self._tmp.name, CACHES=ONBELLEK)
        a.enable()
        self.addCleanup(a.disable)
        cache.clear()                       # test önbelleği AÇILDIKTAN sonra temizlenmeli (testler arası sızıntı olmasın)
        self.addCleanup(cache.clear)
        U = get_user_model()
        self.kullanicilar = {
            "yonetici": U.objects.create_superuser("yonetici", password="Guclu-Parola-9"),
            "muhasebe": rol_kullanici("muhasebe", "Muhasebe"),
            "goruntuleyici": rol_kullanici("goruntuleyici", "Görüntüleyici"),
            "kasiyer": rol_kullanici("kasiyer", "Kasiyer"),
            "rolsuz": rol_kullanici("rolsuz"),
        }
        self.cari = Cari.objects.create(unvan="YETKİ CARİ")
        self.belge = Belge.objects.create(cari=self.cari, tur="ALIS_FISI", tarih=date(2026, 1, 5),
                                          tutar_kurus=10000, evrak_no="1")
        self.mut = EkstreMutabakat.objects.create(cari=self.cari, ekstre_tarihi=date(2026, 1, 31),
                                                  ekstre_bakiye_kurus=10000)
        self.ofis = Hesap.objects.get(ad="Ofis Kasa")
        self.h_ofis = KasaHareketi.objects.create(hesap=self.ofis, yon=GIRIS, tutar_kurus=900000, tarih=date(2026, 1, 5))
        png = lambda n: SimpleUploadedFile(f"{n}.png", PNG + n.encode())
        self.ek_belge = es.ek_ekle(self.belge, png("b"))
        self.ek_ofis = es.ek_ekle(self.h_ofis, png("o"))

    def giris(self, rol):
        self.client.logout()
        if rol != "anonim":
            self.client.force_login(self.kullanicilar[rol])

    def durum(self, rol, url, yontem="get", **veri):
        self.giris(rol)
        return getattr(self.client, yontem)(url, veri).status_code


class YetenekFonksiyonlariTests(YetkiTemel):
    def test_yetenek_kumeleri(self):
        K = self.kullanicilar
        self.assertEqual(yetki.yetenekler(K["yonetici"]), yetki.YONETICI_YETENEKLERI)
        self.assertIn("yonetim", yetki.yetenekler(K["yonetici"]))
        for rol in ("muhasebe", "goruntuleyici", "kasiyer", "rolsuz"):
            self.assertNotIn("yonetim", yetki.yetenekler(K[rol]), rol)
        self.assertEqual(yetki.yetenekler(K["rolsuz"]), frozenset())
        self.assertFalse({"goruntule", "ek_yaz", "veri_gir"} & yetki.yetenekler(K["kasiyer"]))
        self.assertFalse({"kasa_yaz", "ek_yaz", "veri_gir"} & yetki.yetenekler(K["goruntuleyici"]))
        self.assertTrue({"kasa_yaz", "ek_yaz", "veri_gir", "goruntule"} <= yetki.yetenekler(K["muhasebe"]))

    def test_pasif_ve_anonim_kullanici_yetkisiz(self):
        K = self.kullanicilar
        K["muhasebe"].is_active = False
        self.assertEqual(yetki.yetenekler(K["muhasebe"]), frozenset())
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(yetki.yetenekler(AnonymousUser()), frozenset())

    def test_pasif_kullanici_oturum_acamaz(self):
        K = self.kullanicilar
        K["muhasebe"].is_active = False
        K["muhasebe"].save()
        self.client.force_login(K["muhasebe"])
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])

    def test_gorunur_kasalar(self):
        K = self.kullanicilar
        self.assertEqual([h.ad for h in yetki.gorunur_kasalar(K["kasiyer"])], ["Ofis Kasa"])
        for rol in ("yonetici", "muhasebe", "goruntuleyici"):
            self.assertEqual([h.ad for h in yetki.gorunur_kasalar(K[rol])], ["Ofis Kasa"], rol)

    def test_rol_etiketi(self):
        K = self.kullanicilar
        self.assertEqual([yetki.rol_etiketi(K[r]) for r in ROLLER],
                         ["Yönetici", "Muhasebe", "Görüntüleyici", "Kasiyer", "Rolsüz"])


class SayfaYetkiMatrisiTests(YetkiTemel):
    """Her sayfa × her rol. Sıra: yönetici, muhasebe, görüntüleyici, kasiyer, rolsüz, anonim."""

    SIRA = ("yonetici", "muhasebe", "goruntuleyici", "kasiyer", "rolsuz", "anonim")

    def kontrol(self, ad, url, beklenen):
        for rol, bek in zip(self.SIRA, beklenen):
            self.assertEqual(self.durum(rol, url), bek, f"{ad} / {rol}")

    def test_cari_tarafi_sayfalari(self):
        cari_sayfalari = (200, 200, 200, 403, 403, 302)
        for ad, url in (("odeme_listesi", reverse("odeme_listesi")), ("mutabakat", reverse("mutabakat_liste")),
                        ("mutabakat_detay", reverse("mutabakat_detay", args=[self.mut.pk])),
                        ("ekstre", reverse("cari_ekstre", args=[self.cari.pk])), ("ek_depo", reverse("ek_depo")),
                        ("belge_ekleri", reverse("ek_sahip", args=["belge", self.belge.pk])),
                        ("cari_ekleri", reverse("ek_sahip", args=["cari", self.cari.pk])),
                        ("ek_indir_belge", reverse("ek_indir", args=[self.ek_belge.pk]))):
            self.kontrol(ad, url, cari_sayfalari)

    def test_ana_sayfa_kasiyeri_kasaya_yollar(self):
        self.kontrol("dashboard", reverse("dashboard"), (200, 200, 200, 302, 403, 302))
        self.giris("kasiyer")
        self.assertEqual(self.client.get(reverse("dashboard"))["Location"], reverse("kasa"))

    def test_kasa_sayfalari(self):
        self.kontrol("kasa", reverse("kasa"), (200, 200, 200, 200, 403, 302))
        self.kontrol("gun_sonu", reverse("kasa_gun_sonu"), (200, 200, 200, 200, 403, 302))
        self.kontrol("ofis_kasa_eki", reverse("ek_sahip", args=["kasa", self.h_ofis.pk]), (200, 200, 200, 200, 403, 302))
        self.kontrol("ofis_kasa_eki_indir", reverse("ek_indir", args=[self.ek_ofis.pk]), (200, 200, 200, 200, 403, 302))

    def test_yalniz_yonetici_sayfalari(self):
        for ad in ("yedek_sayfasi", "gunluk_sayfasi"):
            self.kontrol(ad, reverse(ad), (200, 403, 403, 403, 403, 302))

    def test_yonetim_paneline_girebilenler(self):
        for rol, bek in (("yonetici", 200), ("muhasebe", 200), ("goruntuleyici", 302), ("kasiyer", 302), ("rolsuz", 302)):
            self.assertEqual(self.durum(rol, reverse("admin:index")), bek, rol)

    def test_menu_role_gore(self):
        self.giris("kasiyer")
        r = self.client.get(reverse("kasa"))
        self.assertContains(r, "Kasa")
        self.assertNotContains(r, "Genel bakış")
        self.assertNotContains(r, "Ödeme listesi")
        self.assertNotContains(r, "Veri girişi")
        self.assertNotContains(r, "Yedek")
        self.assertContains(r, "Kasiyer")
        self.giris("muhasebe")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Genel bakış")
        self.assertContains(r, "Veri girişi")
        self.assertNotContains(r, ">Günlük<")
        self.giris("yonetici")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, ">Günlük<")
        self.assertContains(r, ">Yedek<")

    def test_403_sayfasi_rolu_gosterir(self):
        self.giris("kasiyer")
        r = self.client.get(reverse("odeme_listesi"))
        self.assertContains(r, "yetkiniz yok", status_code=403)
        self.assertContains(r, "Kasiyer", status_code=403)


class YazmaYetkiMatrisiTests(YetkiTemel):
    def kasa_formu(self, hesap):
        return {"tarih": date.today().isoformat(), "yon": "GIRIS", "tutar_kurus": "10,00", "kdv_modu": "BILINMIYOR",
                "aciklama": "yetki testi"}

    def test_kasa_kaydi_girme(self):
        for rol, bek in (("yonetici", 302), ("muhasebe", 302), ("kasiyer", 302), ("goruntuleyici", 403), ("rolsuz", 403)):
            n = KasaHareketi.objects.filter(aciklama="yetki testi").count()
            self.assertEqual(self.durum(rol, f"{reverse('kasa')}?hesap={self.ofis.pk}", "post", **self.kasa_formu(self.ofis)), bek, rol)
            yeni = KasaHareketi.objects.filter(aciklama="yetki testi").count()
            self.assertEqual(yeni - n, 1 if bek == 302 else 0, rol)

    def test_olmayan_kasa_idsi_cokmez(self):
        self.assertEqual(self.durum("kasiyer", f"{reverse('kasa')}?hesap=99999"), 200)

    def test_kasa_iptali(self):
        for rol, bek in (("goruntuleyici", 403), ("rolsuz", 403)):
            self.assertEqual(self.durum(rol, reverse("kasa_hareket_iptal", args=[self.h_ofis.pk]), "post", neden="x"), bek, rol)
        self.assertEqual(self.durum("kasiyer", reverse("kasa_hareket_iptal", args=[self.h_ofis.pk]), "post", neden="x"), 302)
        self.h_ofis.refresh_from_db()
        self.assertTrue(self.h_ofis.iptal)

    def test_gun_sonu_kapatma(self):
        d = date.today().replace(day=1) - __import__("datetime").timedelta(days=1)
        veri = {"tarih": d.isoformat(), "sayilan": "0,00"}
        KasaHareketi.objects.create(hesap=self.ofis, yon=GIRIS, tutar_kurus=100, tarih=d)
        for rol in ("goruntuleyici", "rolsuz"):
            self.assertEqual(self.durum(rol, reverse("kasa_gun_sonu"), "post", **veri), 403, rol)
        self.assertEqual(self.durum("kasiyer", reverse("kasa_gun_sonu"), "post", **veri), 302)

    def test_ek_yukleme_ve_kaldirma(self):
        def yukle(rol, tur, pk, ad):
            self.giris(rol)
            return self.client.post(reverse("ek_sahip", args=[tur, pk]), {"dosyalar": SimpleUploadedFile(ad, PNG + ad.encode())}).status_code
        # cari tarafı: yalnızca muhasebe/yönetici
        self.assertEqual(yukle("muhasebe", "belge", self.belge.pk, "m1.png"), 302)
        self.assertEqual(yukle("yonetici", "belge", self.belge.pk, "y1.png"), 302)
        for rol in ("goruntuleyici", "kasiyer", "rolsuz"):
            self.assertEqual(yukle(rol, "belge", self.belge.pk, f"{rol}.png"), 403, rol)
        # kasa tarafı: kasiyer yalnızca Ofis Kasa'ya; görüntüleyici hiçbirine
        self.assertEqual(yukle("kasiyer", "kasa", self.h_ofis.pk, "k1.png"), 302)
        self.assertEqual(yukle("goruntuleyici", "kasa", self.h_ofis.pk, "g1.png"), 403)
        self.assertEqual(self.belge.ekler.count(), 3)                      # b + m1 + y1
        # kaldırma
        for rol, ek, bek in (("goruntuleyici", self.ek_belge, 403), ("kasiyer", self.ek_belge, 403),
                             ("kasiyer", self.ek_ofis, 302), ("muhasebe", self.ek_belge, 302)):
            self.assertEqual(self.durum(rol, reverse("ek_kaldir", args=[ek.pk]), "post", neden="x"), bek, f"{rol} {ek.pk}")

    def test_yedek_alma_yalniz_yonetici(self):
        for rol in ("muhasebe", "goruntuleyici", "kasiyer", "rolsuz"):
            self.assertEqual(self.durum(rol, reverse("yedek_al"), "post"), 403, rol)

    def test_goruntuleyici_ekranda_yazma_dugmesi_gormez(self):
        self.giris("goruntuleyici")
        r = self.client.get(reverse("kasa"))
        self.assertNotContains(r, "Yeni kasa hareketi")
        self.assertNotContains(r, "kasa/hareket/")                          # iptal formu yok
        r = self.client.get(reverse("ek_sahip", args=["belge", self.belge.pk]))
        self.assertNotContains(r, "Dosya ekle")
        self.assertNotContains(r, "Kaldır")
        self.assertContains(r, "b.png")                                     # ama görebilir
        r = self.client.get(reverse("kasa_gun_sonu"))
        self.assertNotContains(r, "Kapat ve kilitle")
        self.giris("muhasebe")
        self.assertContains(self.client.get(reverse("kasa")), "Yeni kasa hareketi")


class YonetimPaneliYetkiTests(YetkiTemel):
    def test_muhasebe_paneli(self):
        self.giris("muhasebe")
        izinli = [reverse("admin:defter_belge_changelist"), reverse("admin:defter_belge_add"),
                  reverse("admin:defter_cari_add"), reverse("admin:defter_kasahareketi_changelist"),
                  reverse("admin:defter_hesap_changelist"), reverse("admin:defter_ek_changelist"),
                  reverse("admin:defter_gunsonu_changelist")]
        for u in izinli:
            self.assertEqual(self.client.get(u).status_code, 200, u)
        yasak = [reverse("admin:defter_hesap_add"), reverse("admin:defter_islemgunlugu_changelist"),
                 reverse("admin:auth_user_changelist"), reverse("admin:auth_group_changelist"),
                 reverse("admin:defter_ek_add")]
        for u in yasak:
            self.assertEqual(self.client.get(u).status_code, 403, u)

    def test_muhasebe_hesap_ve_kilit_degistiremez(self):
        self.giris("muhasebe")
        gs_kapat = __import__("defter.kasa_servisi", fromlist=["x"]).gun_sonu_kapat(
            self.ofis, date(2026, 1, 5), 900000, bugun=date(2026, 1, 6))
        self.assertEqual(self.client.post(reverse("admin:defter_gunsonu_change", args=[gs_kapat.pk]), {"kilitli": ""}).status_code, 403)
        gs_kapat.refresh_from_db()
        self.assertTrue(gs_kapat.kilitli)
        self.assertEqual(self.client.post(reverse("admin:defter_hesap_change", args=[self.ofis.pk]),
                                          {"ad": "Ofis Kasa", "tur": "KASA", "acilis_bakiye_kurus": "0"}).status_code, 403)
        # yönetici kilidi kaldırabilir
        self.giris("yonetici")
        self.assertEqual(self.client.get(reverse("admin:defter_gunsonu_change", args=[gs_kapat.pk])).status_code, 200)

    def test_hesap_ve_kilit_izni_yanlislikla_verilse_bile_yalniz_yonetici(self):
        """İkinci güvence: bir yönetici Muhasebe'ye 'change' izni verse bile hesap ayarı ve kilit kaldırma yalnızca yöneticidir."""
        muh = self.kullanicilar["muhasebe"]
        for kod in ("change_hesap", "add_hesap", "change_gunsonu"):
            muh.user_permissions.add(Permission.objects.get(codename=kod))
        gs = __import__("defter.kasa_servisi", fromlist=["x"]).gun_sonu_kapat(
            self.ofis, date(2026, 1, 5), 900000, bugun=date(2026, 1, 6))
        self.giris("muhasebe")
        # Görme izni olan kullanıcıya düzenleme sayfası SALT OKUNUR açılır: "Kaydet" düğmesi olmamalı, POST reddedilmeli.
        r = self.client.get(reverse("admin:defter_hesap_change", args=[self.ofis.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="_save"')
        self.assertEqual(self.client.post(reverse("admin:defter_hesap_change", args=[self.ofis.pk]),
                                          {"ad": "Ofis Kasa", "tur": "KASA", "acilis_bakiye_kurus": "999,00"}).status_code, 403)
        self.ofis.refresh_from_db()
        self.assertEqual(self.ofis.acilis_bakiye_kurus, 0)
        self.assertEqual(self.client.get(reverse("admin:defter_hesap_add")).status_code, 403)
        r = self.client.get(reverse("admin:defter_gunsonu_change", args=[gs.pk]))
        self.assertNotContains(r, 'name="_save"')
        self.assertEqual(self.client.post(reverse("admin:defter_gunsonu_change", args=[gs.pk]), {"kilitli": ""}).status_code, 403)
        gs.refresh_from_db()
        self.assertTrue(gs.kilitli)
        # Yönetici aynı sayfada düzenleyebilir
        self.giris("yonetici")
        self.assertContains(self.client.get(reverse("admin:defter_gunsonu_change", args=[gs.pk])), 'name="_save"')

    def test_muhasebe_silemez(self):
        self.giris("muhasebe")
        self.assertEqual(self.client.post(reverse("admin:defter_cari_delete", args=[self.cari.pk]), {"post": "yes"}).status_code, 403)
        self.assertTrue(Cari.objects.filter(pk=self.cari.pk).exists())


class RolKurulumuTests(YetkiTemel):
    def test_gruplar_ve_izinler(self):
        self.assertEqual(sorted(Group.objects.filter(name__in=yetki.ROL_YETENEKLERI).values_list("name", flat=True)),
                         sorted(yetki.ROL_YETENEKLERI))
        beklenen = {f"{h}_{m}" for m in MUHASEBE_YAZAR for h in ("add", "change", "view")} | {f"view_{m}" for m in MUHASEBE_OKUR}
        muh = set(Group.objects.get(name="Muhasebe").permissions.values_list("codename", flat=True))
        self.assertEqual(muh, beklenen)
        self.assertFalse([k for k in muh if k.startswith("delete_")])
        for ad in ("Kasiyer", "Görüntüleyici"):
            self.assertEqual(Group.objects.get(name=ad).permissions.count(), 0, ad)

    def test_idempotent_ve_onarir(self):
        g = Group.objects.get(name="Muhasebe")
        g.permissions.add(Permission.objects.get(codename="delete_belge"))          # biri izni fazla verdi
        Group.objects.get(name="Kasiyer").permissions.add(Permission.objects.get(codename="view_belge"))
        n = Group.objects.count()
        out = StringIO()
        call_command("rolleri_kur", stdout=out)
        call_command("rolleri_kur", stdout=out)
        self.assertEqual(Group.objects.count(), n)
        self.assertFalse(g.permissions.filter(codename="delete_belge").exists())
        self.assertEqual(Group.objects.get(name="Kasiyer").permissions.count(), 0)

    def test_is_staff_senkronu_ve_gunluk(self):
        u = rol_kullanici("yeni")
        self.assertFalse(u.is_staff)
        u.groups.add(Group.objects.get(name="Muhasebe"))
        u.refresh_from_db()
        self.assertTrue(u.is_staff)
        u.groups.add(Group.objects.get(name="Kasiyer"))
        u.groups.remove(Group.objects.get(name="Muhasebe"))
        u.refresh_from_db()
        self.assertFalse(u.is_staff)                                          # muhasebe gidince panel de gider
        g = IslemGunlugu.objects.filter(model="Kullanıcı", nesne_id=u.pk, ayrinti__icontains="rolleri").first()
        self.assertEqual(g.degisiklik["Roller"], [None, "Kasiyer"])           # rol değişikliği günlükte
        self.assertEqual(IslemGunlugu.objects.filter(ayrinti__icontains="rolleri", nesne_id=u.pk).count(), 3)

    def test_yonetici_staff_kalir(self):
        y = self.kullanicilar["yonetici"]
        y.groups.add(Group.objects.get(name="Kasiyer"))
        y.refresh_from_db()
        self.assertTrue(y.is_staff)

    def test_kullanici_olustur_komutu(self):
        out = StringIO()
        call_command("kullanici_olustur", "ayse", "--rol", "Kasiyer", "--parola", "Guclu-Parola-77", stdout=out)
        u = get_user_model().objects.get(username="ayse")
        self.assertEqual(yetki.rol_etiketi(u), "Kasiyer")
        self.assertFalse(u.is_staff)
        self.assertTrue(authenticate(username="ayse", password="Guclu-Parola-77"))
        with self.assertRaises(CommandError):
            call_command("kullanici_olustur", "ayse", "--rol", "Muhasebe", "--parola", "Guclu-Parola-77")   # var
        with self.assertRaises(CommandError):
            call_command("kullanici_olustur", "veli", "--rol", "Muhasebe", "--parola", "12345678")         # zayıf
        with self.assertRaises(CommandError):
            call_command("kullanici_olustur", "veli", "--rol", "Patron", "--parola", "Guclu-Parola-77")     # rol yok
        self.assertFalse(get_user_model().objects.filter(username="veli").exists())
        call_command("kullanici_olustur", "mehmet", "--rol", "Muhasebe", "--parola", "Guclu-Parola-77", stdout=out)
        self.assertTrue(get_user_model().objects.get(username="mehmet").is_staff)


class GirisCikisTests(YetkiTemel):
    def test_giris_sayfasi_ve_basarili_giris(self):
        self.client.logout()
        r = self.client.get(reverse("giris"))
        self.assertContains(r, "Kullanıcı adı")
        r = self.client.post(reverse("giris"), {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_yetkisiz_sayfa_giristen_sonra_oraya_doner(self):
        self.client.logout()
        r = self.client.get(reverse("odeme_listesi"))
        self.assertEqual(r["Location"], f"{reverse('giris')}?next={reverse('odeme_listesi')}")
        r = self.client.post(r["Location"], {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.assertRedirects(r, reverse("odeme_listesi"), fetch_redirect_response=False)

    def test_dis_adrese_yonlendirme_yok(self):
        self.client.logout()
        r = self.client.post(f"{reverse('giris')}?next=https://kotu.example/", {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("kotu.example", r["Location"])

    def test_yanlis_parola(self):
        self.client.logout()
        r = self.client.post(reverse("giris"), {"username": "muhasebe", "password": "yanlis"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "doğru kullanıcı adı")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_cikis_yalniz_post_ve_oturumu_kapatir(self):
        self.giris("muhasebe")
        self.assertEqual(self.client.get(reverse("cikis")).status_code, 405)         # eski hata: GET bağlantısı 405 veriyordu
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)     # hâlâ açık
        r = self.client.post(reverse("cikis"))
        self.assertRedirects(r, reverse("giris"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        self.assertEqual(IslemGunlugu.objects.filter(islem="CIKIS", kullanici="muhasebe").count(), 1)

    def test_baslik_cikis_baglantisi_post_formudur(self):
        self.giris("muhasebe")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, f'action="{reverse("cikis")}"')
        self.assertNotContains(r, "admin/logout")

    def test_cikis_icin_oturum_gerekir(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("cikis")).status_code, 302)


class GirisKilidiTests(YetkiTemel):
    def yanlis(self, ad="muhasebe", n=1, url=None):
        for _ in range(n):
            r = self.client.post(url or reverse("giris"), {"username": ad, "password": "yanlis-parola"})
        return r

    def test_bes_hatadan_sonra_dogru_parola_bile_reddedilir(self):
        self.client.logout()
        self.yanlis(n=4)
        r = self.client.post(reverse("giris"), {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.assertEqual(r.status_code, 302)                                         # 4 hatadan sonra hâlâ girebilir
        self.client.logout()
        self.yanlis(n=5)
        r = self.client.post(reverse("giris"), {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Çok fazla hatalı deneme")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_kilit_baska_kullaniciyi_etkilemez_ve_kilit_gunlukte(self):
        self.client.logout()
        self.yanlis("muhasebe", 5)
        r = self.client.post(reverse("giris"), {"username": "kasiyer", "password": "Guclu-Parola-9"})
        self.assertEqual(r.status_code, 302)
        kilit = IslemGunlugu.objects.filter(islem="GIRIS_HATASI", ayrinti__icontains="geçici olarak kapatıldı")
        self.assertEqual(kilit.count(), 1)
        self.assertEqual(kilit.get().kullanici, "muhasebe")

    def test_basarili_giris_sayaci_sifirlar(self):
        self.client.logout()
        self.yanlis(n=4)
        self.client.post(reverse("giris"), {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.client.logout()
        self.yanlis(n=4)                                                             # sayaç sıfırlandığı için kilit yok
        r = self.client.post(reverse("giris"), {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.assertEqual(r.status_code, 302)

    def test_buyuk_kucuk_harf_ayni_kullanici_sayilir(self):
        self.client.logout()
        for ad in ("Muhasebe", "MUHASEBE", "muhasebe", "MuHaSeBe", "muhasebe "):
            self.yanlis(ad)
        r = self.client.post(reverse("giris"), {"username": "muhasebe", "password": "Guclu-Parola-9"})
        self.assertContains(r, "Çok fazla hatalı deneme")

    def test_yonetim_paneli_girisi_de_kilitlenir(self):
        self.client.logout()
        panel = reverse("admin:login")
        self.yanlis("muhasebe", 5, url=panel)
        r = self.client.post(panel, {"username": "muhasebe", "password": "Guclu-Parola-9", "next": "/admin/"})
        self.assertContains(r, "Çok fazla hatalı deneme")


class ParolaDegistirmeTests(YetkiTemel):
    def test_giris_gerekli(self):
        self.client.logout()
        r = self.client.get(reverse("parola"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/giris/", r["Location"])

    def test_degistirme_ve_kurallar(self):
        self.giris("kasiyer")
        yol = reverse("parola")
        r = self.client.post(yol, {"old_password": "yanlis", "new_password1": "Yeni-Parola-55", "new_password2": "Yeni-Parola-55"})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(yol, {"old_password": "Guclu-Parola-9", "new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(r.status_code, 200)                                          # zayıf parola
        self.assertTrue(authenticate(username="kasiyer", password="Guclu-Parola-9"))
        r = self.client.post(yol, {"old_password": "Guclu-Parola-9", "new_password1": "Yeni-Parola-55", "new_password2": "Yeni-Parola-55"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(authenticate(username="kasiyer", password="Yeni-Parola-55"))
        self.assertIsNone(authenticate(username="kasiyer", password="Guclu-Parola-9"))
        self.assertEqual(self.client.get(reverse("kasa")).status_code, 200)           # oturum açık kalır
        g = IslemGunlugu.objects.filter(ayrinti__icontains="kendi parolasını").get()
        self.assertEqual(g.kullanici, "kasiyer")
        self.assertNotIn("Yeni-Parola-55", str(g.degisiklik) + g.ayrinti)
