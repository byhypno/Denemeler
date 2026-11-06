"""Arayüz (tasarım sistemi) testleri: kontrast, token tamlığı, çevrimdışılık, erişilebilirlik, simge/yazı tipi varlığı."""
import re
from datetime import date
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from .models import Belge, Cari
from .templatetags.defter_filtreleri import ikon, kurus_say, kurus_tl
from .test_yardimci import rol_kullanici

BASE = Path(__file__).resolve().parent
STATIK = BASE / "static" / "defter"
CSS = (STATIK / "css" / "cari.css").read_text(encoding="utf-8")
ADMIN_CSS = (STATIK / "css" / "admin_tema.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------- WCAG kontrast
def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def oran(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def blok(css, baslangic):
    """`baslangic` ile başlayan CSS bloğunun {...} içeriği (iç içe küme parantezi destekli)."""
    i = css.index(baslangic)
    j = css.index("{", i)
    derinlik, k = 1, j + 1
    while derinlik:
        derinlik += {"{": 1, "}": -1}.get(css[k], 0)
        k += 1
    return css[j + 1:k - 1]


def degiskenler(metin):
    return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})\s*;", metin))


ACIK = degiskenler(blok(CSS, ":root {\n  color-scheme: light;"))
KOYU = degiskenler(blok(CSS, ':root[data-tema="koyu"]'))
KOYU_SISTEM = degiskenler(blok(blok(CSS, "@media (prefers-color-scheme: dark)"), ':root:not([data-tema="acik"])'))

# (ön plan, arka plan, en az oran, açıklama)
CIFTLER = [
    ("--murekkep", "--sayfa", 7, "ana metin / yüzey"), ("--murekkep", "--kagit", 7, "ana metin / zemin"),
    ("--murekkep", "--sayfa-2", 7, "ana metin / ikincil yüzey"),
    ("--murekkep-2", "--sayfa", 4.5, "ikincil metin / yüzey"), ("--murekkep-2", "--kagit", 4.5, "ikincil metin / zemin"),
    ("--murekkep-2", "--sayfa-2", 4.5, "ikincil metin / ikincil yüzey"), ("--murekkep-3", "--sayfa", 4.5, "ipucu metni"),
    ("--cizgi-girdi", "--sayfa", 3, "form kutusu kenarı"),
    ("--yesil-uzeri", "--yesil", 4.5, "birincil düğme"), ("--yesil", "--sayfa", 4.5, "bağlantı / yüzey"),
    ("--yesil", "--kagit", 4.5, "bağlantı / zemin"), ("--yesil-acik-metin", "--yesil-acik", 4.5, "tamam etiketi"),
    ("--kirmizi", "--kirmizi-zemin", 4.5, "hata etiketi"), ("--kirmizi", "--sayfa", 4.5, "eksi tutar"),
    ("--amber", "--amber-zemin", 4.5, "uyarı etiketi"), ("--mavi", "--mavi-zemin", 4.5, "bilgi etiketi"),
    ("--yan-metin", "--yan-bg", 7, "menü metni"), ("--yan-metin-2", "--yan-bg", 4.5, "menü ikincil metin"),
    ("--yan-aktif-metin", "--yan-aktif-bg", 4.5, "seçili menü"), ("--pirinc", "--yan-bg", 3, "seçili menü işareti"),
    ("--odak", "--sayfa", 3, "odak halkası / yüzey"), ("--odak", "--kagit", 3, "odak halkası / zemin"),
    ("--odak-yan", "--yan-bg", 3, "odak halkası / menü"),
    ("--g-alis", "--sayfa", 3, "grafik alış"), ("--g-odeme", "--sayfa", 3, "grafik ödeme"), ("--g-iade", "--sayfa", 3, "grafik iade"),
    ("--g-bakiye", "--sayfa", 7, "grafik bakiye çizgisi"),
]


class KontrastTests(TestCase):
    def test_token_bloklari_okunabildi(self):
        for ad, t in (("açık", ACIK), ("koyu", KOYU), ("koyu(sistem)", KOYU_SISTEM)):
            self.assertGreater(len(t), 30, ad)

    def test_acik_ve_koyu_tema_wcag_aa(self):
        sorunlar = []
        for ad, t in (("açık", ACIK), ("koyu", {**ACIK, **KOYU})):
            for on, arka, en_az, aciklama in CIFTLER:
                r = oran(t[on], t[arka])
                if r < en_az:
                    sorunlar.append(f"{ad}: {aciklama} {t[on]} / {t[arka]} = {r:.2f} < {en_az}")
        self.assertEqual(sorunlar, [])

    def test_elle_koyu_ve_sistem_koyu_bloklari_ayni(self):
        """Aynı koyu palet iki yerde tanımlı (elle seçim + sistem tercihi); ayrışmamalı."""
        self.assertEqual(KOYU, KOYU_SISTEM)

    def test_koyu_tema_tum_renkleri_tanimliyor(self):
        """Koyu blokta unutulan token açık temanın rengiyle kalırdı (ör. beyaz yüzeyde açık metin)."""
        renkli_ortak = {k for k in ACIK if k not in ("--golge-yuzen",)}
        eksik = sorted(k for k in renkli_ortak if k not in KOYU and k not in ("--pirinc",))
        self.assertEqual(eksik, [])

    def test_yonetim_paneli_kontrasti(self):
        def duzey(metin):
            return degiskenler(metin)
        acik = duzey(blok(ADMIN_CSS, 'html[data-theme="light"], :root'))
        koyu = duzey(blok(ADMIN_CSS, 'html[data-theme="dark"]'))
        koyu_sistem = duzey(blok(blok(ADMIN_CSS, "@media (prefers-color-scheme: dark)"), ":root"))
        self.assertEqual({k: v for k, v in koyu.items()}, {k: v for k, v in koyu_sistem.items()})
        ciftler = [("--body-fg", "--body-bg", 7), ("--body-quiet-color", "--body-bg", 4.5), ("--link-fg", "--body-bg", 4.5),
                   ("--button-fg", "--button-bg", 4.5), ("--button-fg", "--default-button-bg", 4.5),
                   ("--header-color", "--header-bg", 4.5), ("--header-link-color", "--header-bg", 4.5),
                   ("--breadcrumbs-link-fg", "--breadcrumbs-bg", 4.5), ("--breadcrumbs-fg", "--breadcrumbs-bg", 4.5),
                   ("--error-fg", "--message-error-bg", 4.5), ("--body-fg", "--message-success-bg", 4.5),
                   ("--body-fg", "--message-warning-bg", 4.5), ("--body-fg", "--message-info-bg", 4.5),
                   ("--button-fg", "--delete-button-bg", 4.5), ("--accent", "--header-bg", 3)]
        sorunlar = []
        for ad, t in (("açık", acik), ("koyu", {**acik, **koyu})):
            ciftler_t = ciftler + [("--object-tools-fg", "--object-tools-bg", 4.5)]
            for on, arka, en_az in ciftler_t:
                if on not in t:               # panelin kendi varsayılanına bırakılmış (--object-tools-fg açık temada)
                    continue
                r = oran(t[on], t[arka])
                if r < en_az:
                    sorunlar.append(f"{ad}: {on} {t[on]} / {arka} {t[arka]} = {r:.2f} < {en_az}")
        self.assertEqual(sorunlar, [])


class TokenTamlikTests(TestCase):
    def test_kullanilan_her_degisken_tanimli(self):
        tanimli = set(re.findall(r"(--[\w-]+)\s*:", CSS))
        kullanilan = set(re.findall(r"var\((--[\w-]+)", CSS))
        # --simge, ::before içinde sınıfa göre yerel tanımlanır (aynı dosyada tanımlı)
        self.assertEqual(sorted(kullanilan - tanimli), [])

    def test_ham_renk_yalniz_token_bloklarinda(self):
        """Bileşenlerde ham renk (#hex) yok: renkler yalnızca token bloklarında ve veri-URI simgelerinde."""
        govde = CSS
        for baslangic in (":root {\n  color-scheme: light;", ':root[data-tema="koyu"]', "@media (prefers-color-scheme: dark) {\n  :root:not"):
            i = govde.index(baslangic)
            govde = govde[:i] + govde[i + len(blok(govde, baslangic)):]
        govde = govde.replace(blok(govde, "@media print"), "")      # yazdırma kâğıda göre sabit renk kullanır
        govde = re.sub(r"url\(\"data:[^)]*\)", "", govde)
        govde = re.sub(r"rgba?\([^)]*\)", "", govde)
        ham = sorted(set(re.findall(r"#[0-9A-Fa-f]{3,8}\b", govde)))
        self.assertEqual(ham, ["#fff"], "bileşenlerde ham renk kullanılmış")   # yalnızca görsel zemini (önizleme)

    def test_yazi_tipi_dosyalari_var(self):
        dosyalar = re.findall(r'url\("\.\./fonts/([^"]+)"\)', (STATIK / "css" / "fontlar.css").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(dosyalar), 10)
        for d in dosyalar:
            self.assertTrue((STATIK / "fonts" / d).is_file(), d)
        for lisans in ("LICENSE-ibm-plex-sans.txt", "LICENSE-barlow-semi-condensed.txt"):
            self.assertTrue((STATIK / "fonts" / lisans).is_file(), lisans)
        self.assertIn("font-display: swap", (STATIK / "css" / "fontlar.css").read_text(encoding="utf-8"))

    def test_tr_karakterleri_ve_lira_yazi_tipinde_var(self):
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools yok")
        for aile in ("ibm-plex-sans-latin%s-400-normal", "barlow-semi-condensed-latin%s-600-normal"):
            cmap = set()
            for alt in ("", "-ext"):
                cmap |= set(TTFont(STATIK / "fonts" / (aile % alt + ".woff2")).getBestCmap())
            eksik = [c for c in "çÇğĞıİöÖşŞüÜ₺−" if ord(c) not in cmap]
            self.assertEqual(eksik, [], aile)

    def test_her_simge_sprite_te_tanimli(self):
        sprite = (BASE / "templates" / "defter" / "_ikonlar.html").read_text(encoding="utf-8")
        tanimli = set(re.findall(r'<symbol id="i-([\w-]+)"', sprite))
        kullanilan = set()
        for p in (BASE / "templates").rglob("*.html"):
            kullanilan |= set(re.findall(r'\{%\s*ikon\s+"([\w-]+)"', p.read_text(encoding="utf-8")))
        kullanilan |= set(re.findall(r"#i-([\w-]+)", (STATIK / "js" / "arayuz.js").read_text(encoding="utf-8")))
        self.assertEqual(sorted(kullanilan - tanimli), [])

    def test_ikon_etiketi_ekran_okuyucudan_gizli(self):
        h = str(ikon("kasa", "kucuk"))
        self.assertIn('aria-hidden="true"', h)
        self.assertIn('href="#i-kasa"', h)
        self.assertIn("ikon kucuk", h)

    def test_eksi_tutar_renk_ve_isaretle(self):
        self.assertEqual(str(kurus_tl(-123450)), '<span class="eksi">-1.234,50 ₺</span>')
        self.assertEqual(str(kurus_say(-5)), '<span class="eksi">-0,05</span>')
        self.assertEqual(str(kurus_tl(123450)), "1.234,50 ₺")
        self.assertEqual(str(kurus_tl(0)), "0,00 ₺")
        self.assertEqual(kurus_tl(None), "—")


class SayfaYapisiTests(TestCase):
    def setUp(self):
        self.k = rol_kullanici("muhasebe", "Muhasebe")
        c = Cari.objects.create(unvan="UI CARİ")
        Belge.objects.create(cari=c, tur="ALIS_FISI", tarih=date(2026, 1, 5), tutar_kurus=10000, evrak_no="1")
        self.c = c
        self.client.force_login(self.k)

    def sayfalar(self):
        return [reverse("dashboard"), reverse("kasa"), reverse("odeme_listesi"), reverse("mutabakat_liste"),
                reverse("ek_depo"), reverse("cari_ekstre", args=[self.c.pk]), reverse("kasa_gun_sonu"),
                reverse("ek_sahip", args=["cari", self.c.pk]), reverse("parola")]

    def test_erisilebilirlik_iskeleti(self):
        for url in self.sayfalar():
            h = self.client.get(url).content.decode()
            self.assertIn('<html lang="tr">', h, url)
            self.assertIn('class="atla" href="#icerik"', h, url)
            self.assertRegex(h, r'<main class="icerik" id="icerik"', url)
            self.assertEqual(h.count("<h1"), 1, f"{url}: tek <h1> olmalı")
            self.assertLessEqual(h.count('aria-current="page"'), 1, url)
            self.assertIn('aria-label="Ana menü"', h, url)
            self.assertIn('aria-label="Sayfalar"', h, url)
            self.assertIn('id="yan-ac"', h, url)
            self.assertIn('aria-controls="yan"', h, url)
            self.assertIn('name="color-scheme"', h, url)

    def test_menude_gecerli_sayfa_isaretli(self):
        h = self.client.get(reverse("odeme_listesi")).content.decode()
        self.assertRegex(h, r'<a href="/odemeler/" aria-current="page">')
        h = self.client.get(reverse("kasa")).content.decode()
        self.assertRegex(h, r'<a href="/kasa/" aria-current="page">')

    def test_tema_betigi_stilden_once_calisir(self):
        h = self.client.get(reverse("dashboard")).content.decode()
        self.assertLess(h.index("cari_tema"), h.index("cari.css"))        # yanıp sönme olmasın
        self.assertIn("arayuz.js", h)
        self.assertIn('id="tema-dugme"', h)

    def test_tum_sayfalar_cevrimdisi_calisir(self):
        """Hiçbir sayfa dış adrese (CDN, yazı tipi sunucusu...) bağlanmamalı."""
        dis = re.compile(r'(?:href|src|action)="(https?:)?//(?!127\.0\.0\.1|localhost)[^"]+"|@import|url\(\s*["\']?https?:')
        for url in self.sayfalar() + [reverse("giris")]:
            h = self.client.get(url).content.decode()
            self.assertIsNone(dis.search(h), f"{url}: dış kaynak var -> {dis.search(h)}")
        for dosya in list((STATIK / "css").glob("*.css")) + list((STATIK / "js").glob("*.js")):
            metin = dosya.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r'https?://(?!www\.w3\.org)', metin.replace("http://www.w3.org/2000/svg", "")),
                              f"{dosya.name}: dış adres")

    def test_giris_sayfasi_kabuksuz_ve_markali(self):
        self.client.logout()
        h = self.client.get(reverse("giris")).content.decode()
        self.assertNotIn('class="yan"', h)
        self.assertIn("giris-sayfasi", h)
        self.assertIn("Cari <span>Program</span>", h)
        self.assertEqual(h.count("<h1"), 1)
        self.assertIn('autocomplete="username"', h)
        self.assertIn('autocomplete="current-password"', h)

    def test_gorsel_onizlemelerin_alt_metni_var(self):
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from . import ek_servisi as es
        with tempfile.TemporaryDirectory() as d, override_settings(EK_DIZINI=d):
            es.ek_ekle(self.c, SimpleUploadedFile("fis.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20))
            h = self.client.get(reverse("ek_sahip", args=["cari", self.c.pk])).content.decode()
        for img in re.findall(r"<img[^>]*>", h):
            self.assertRegex(img, r'alt="[^"]+"', img)

    def test_iletilerin_erisilebilir_rolleri(self):
        """Hata iletisi role=alert (hemen okunur), başarı/bilgi role=status (nazikçe duyurulur)."""
        from .models import Hesap, KasaHareketi
        ofis = Hesap.objects.get(ad="Ofis Kasa")
        h = KasaHareketi.objects.create(hesap=ofis, yon="GIRIS", tutar_kurus=100, tarih=date(2026, 1, 1))
        r = self.client.post(reverse("kasa_hareket_iptal", args=[h.pk]), {"neden": ""}, follow=True)
        self.assertRegex(r.content.decode(), r'<div class="mesaj error" role="alert">İptal için neden yazın')
        r = self.client.post(reverse("kasa"), {"tarih": date.today().isoformat(), "yon": "GIRIS", "tutar_kurus": "5,00",
                                               "kdv_modu": "BILINMIYOR"}, follow=True)
        self.assertRegex(r.content.decode(), r'<div class="mesaj success" role="status">Kaydedildi')

    def test_yonetim_paneli_temali(self):
        yon = rol_kullanici("m2", "Muhasebe")
        self.client.force_login(yon)
        h = self.client.get(reverse("admin:index")).content.decode()
        self.assertIn("admin_tema.css", h)
        self.assertIn("fontlar.css", h)
        self.assertIn("cari_tema", h)                                    # tema uygulamayla eşleşir
        self.assertLess(h.index("cari_tema"), h.index("theme.js"))       # panelin kendi betiğinden ÖNCE
