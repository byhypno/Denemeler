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
    ("--metin", "--zemin", 7, "ana metin / zemin"), ("--metin", "--kart", 7, "ana metin / kart"),
    ("--metin", "--kart-2", 7, "ana metin / ikincil yüzey"),
    ("--metin-2", "--zemin", 4.5, "ikincil metin / zemin"), ("--metin-2", "--kart", 4.5, "ikincil metin / kart"),
    ("--metin-2", "--kart-2", 4.5, "ikincil metin / ikincil yüzey"),
    ("--metin-3", "--kart", 4.5, "ipucu metni"), ("--metin-3", "--zemin", 4.5, "ipucu metni / zemin"),
    ("--cizgi-girdi", "--kart", 3, "form kutusu kenarı"),
    ("--vurgu-uzeri", "--vurgu", 4.5, "birincil düğme"), ("--vurgu-uzeri", "--vurgu-hover", 4.5, "düğme (üzerine gelince)"),
    ("--vurgu", "--kart", 4.5, "bağlantı / kart"), ("--vurgu", "--zemin", 4.5, "bağlantı / zemin"),
    ("--vurgu-metin", "--vurgu-zemin", 4.5, "vurgu etiketi"),
    ("--pozitif", "--pozitif-zemin", 4.5, "tamam etiketi"), ("--pozitif", "--kart", 4.5, "olumlu metin"),
    ("--negatif", "--negatif-zemin", 4.5, "hata etiketi"), ("--negatif", "--kart", 4.5, "eksi tutar"),
    ("--uyari", "--uyari-zemin", 4.5, "uyarı etiketi"), ("--bilgi", "--bilgi-zemin", 4.5, "bilgi etiketi"),
    ("--metin", "--yan-bg", 7, "menü metni"), ("--yan-metin-2", "--yan-bg", 4.5, "menü ikincil metin"),
    ("--yan-metin-2", "--yan-hover", 4.5, "menü üzerine gelince"),
    ("--yan-aktif-metin", "--yan-aktif-bg", 4.5, "seçili menü"),
    ("--odak", "--kart", 3, "odak halkası / kart"), ("--odak", "--zemin", 3, "odak halkası / zemin"),
    ("--odak", "--yan-bg", 3, "odak halkası / menü"),
    ("--g-alis", "--kart", 3, "grafik alış"), ("--g-odeme", "--kart", 3, "grafik ödeme"), ("--g-iade", "--kart", 3, "grafik iade"),
    ("--g-bakiye", "--kart", 7, "grafik bakiye çizgisi"),
    ("--ipucu-metin", "--ipucu-bg", 7, "grafik ipucu balonu"),
] + [(f"--av{n}-fg", f"--av{n}-bg", 4.5, f"avatar {n}") for n in range(1, 9)] \
  + [(f"--k{n}", "--kart", 3, f"grafik kategori rengi {n}") for n in range(1, 9)]


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
        renkli_ortak = set(ACIK)
        eksik = sorted(k for k in renkli_ortak if k not in KOYU and k not in ("--marka-1", "--marka-2"))   # marka degradesi iki temada aynı
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
        for lisans in ("LICENSE-plus-jakarta-sans.txt",):
            self.assertTrue((STATIK / "fonts" / lisans).is_file(), lisans)
        self.assertIn("font-display: swap", (STATIK / "css" / "fontlar.css").read_text(encoding="utf-8"))

    def test_tr_karakterleri_ve_lira_yazi_tipinde_var(self):
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools yok")
        for aile in ("plus-jakarta-sans-latin%s-400-normal", "plus-jakarta-sans-latin%s-700-normal"):
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
        self.assertIn("Cari Program", h)
        self.assertIn('alt="Egeser Konteyner Prefabrik ve Çelik Yapılar"', h)         # logo, erişilebilir ad
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


class UiDenetimDuzeltmeTests(TestCase):
    """UI denetiminde bulunan kayma/taşma düzeltmelerinin geri gelmemesi için (CSS/JS kaynağı üzerinden)."""

    def kural(self, secici):
        m = re.search(re.escape(secici) + r"\s*\{([^}]*)\}", CSS)
        self.assertIsNotNone(m, secici)
        return m.group(1)

    def test_kaydirma_kutusu_konumlandirma_baglami_tasir(self):
        """Mutlak konumlu .sr-only öğeleri kaydırma kutusunun dışında kalıp sayfayı yatay kaydırmasın."""
        self.assertIn("position: relative", self.kural(".tablo-kaydir"))
        self.assertIn("position: absolute", self.kural(".sr-only"))

    def test_mesaj_serit_flex_degil(self):
        """Flex olursa içindeki metin/bağlantı ayrı sütunlara bölünür."""
        self.assertNotIn("display: flex", self.kural(".mesaj"))

    def test_kpi_rakami_karta_gore_kuculur_ve_sarar(self):
        self.assertIn("container-type: inline-size", CSS)
        self.assertIn("cqi", CSS)
        self.assertNotRegex(self.kural(".kpi .deger, .ozet .deger"), r"white-space:\s*nowrap")

    def test_kalem_tablosu_dar_ekranda_ezilmez(self):
        self.assertRegex(self.kural(".kalem-tablo"), r"min-width:\s*\d{3}px")

    def test_cekmece_acikken_icerik_inert(self):
        js = (STATIK / "js" / "arayuz.js").read_text(encoding="utf-8")
        self.assertIn(".inert = acik", js)

    def test_baslik_kaynaklari_cumle_duzeninde(self):
        """<title>, H1 ve menüyle tutarlı olsun: 'Ekstre Mutabakatı' gibi Title Case başlık kalmasın."""
        for ad in ("mutabakat_liste", "gunluk", "ek_depo", "odeme_listesi"):
            s = (BASE / "templates" / "defter" / f"{ad}.html").read_text(encoding="utf-8")
            baslik = re.search(r"\{% block baslik %\}(.*?)\{% endblock %\}", s).group(1)
            kelimeler = [k for k in re.split(r"[\s:]+", baslik.split("·")[0]) if k.isalpha()]
            self.assertTrue(all(not k[0].isupper() for k in kelimeler[1:]), f"{ad}: {baslik}")

    def test_yazdirmada_uyari_ve_dugmeler_gizli(self):
        yazdir = blok(CSS, "@media print")
        self.assertIn(".mesaj", yazdir)
        self.assertIn("button", yazdir)

    def test_ekstre_menude_tedarikciler_isaretli(self):
        from .models import Cari
        c = Cari.objects.create(unvan="Menü Tedarik")
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        h = self.client.get(reverse("cari_ekstre", args=[c.pk])).content.decode()
        self.assertRegex(h, r'<a href="/tedarikciler/" aria-current="page">')


class LogoTests(TestCase):
    """Marka logosu: dosyalar, yerleşim, koyu tema varyantı, yazdırma, yönetim paneli."""
    IMG = STATIK / "img"

    def test_dosyalar_var_ve_makul_boyutta(self):
        for ad in ("logo.png", "logo-koyu.png", "logo-sembol.png", "favicon.png"):
            yol = self.IMG / ad
            self.assertTrue(yol.is_file(), ad)
            self.assertLess(yol.stat().st_size, 150_000, ad)            # çevrimdışı/yerel: küçük tutulur
            self.assertEqual(yol.read_bytes()[:8], b"\x89PNG\r\n\x1a\n", ad)

    def test_menu_ve_ust_serit_simge_kullanir(self):
        k = rol_kullanici("m", "Muhasebe")
        self.client.force_login(k)
        h = self.client.get(reverse("dashboard")).content.decode()
        self.assertEqual(h.count('class="marka-logo"'), 2)             # kenar çubuğu + mobil üst şerit
        self.assertIn("img/logo-sembol.png", h)
        self.assertIn('rel="icon"', h)
        self.assertIn("Cari <span>Program</span>", h)                 # bağlantının erişilebilir adı korunur

    def test_giris_sayfasinda_acik_ve_koyu_logo(self):
        h = self.client.get(reverse("giris")).content.decode()
        self.assertIn("img/logo.png", h)
        self.assertIn("img/logo-koyu.png", h)
        self.assertEqual(h.count('alt="Egeser Konteyner'), 1)         # koyu varyant dekoratif: ikinci kez okunmaz
        self.assertIn('rel="icon"', h)

    def test_koyu_tema_kurallari_css_te(self):
        self.assertIn(".logo-koyu { display: none; }", CSS)
        self.assertRegex(CSS, r':root\[data-tema="koyu"\] \.logo-acik \{ display: none; \}')
        self.assertRegex(CSS, r'prefers-color-scheme: dark\) \{\s*:root:not\(\[data-tema="acik"\]\) \.logo-acik')

    def test_yazdirma_logosu_yalniz_girisli_sayfada(self):
        self.assertNotIn("yazdirma-logo", self.client.get(reverse("giris")).content.decode())
        self.client.force_login(rol_kullanici("m", "Muhasebe"))
        h = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn('class="sadece-yazdir yazdirma-logo"', h)
        self.assertIn("img.sadece-yazdir", CSS)

    def test_yonetim_paneli_logosu_ve_favicon(self):
        self.client.force_login(rol_kullanici("y", is_superuser=True, is_staff=True))
        h = self.client.get(reverse("admin:index")).content.decode()
        self.assertIn("admin-logo", h)
        self.assertIn('rel="icon"', h)

    def test_logolar_statik_olarak_sunulur(self):
        for ad in ("logo.png", "logo-koyu.png", "logo-sembol.png", "favicon.png"):
            r = self.client.get(f"/static/defter/img/{ad}")
            self.assertEqual(r.status_code, 200, ad)


class LogoUretTests(TestCase):
    """araclar/logo_uret.py: logo değiştirildiğinde varyantlar doğru üretilmeli (Pillow yoksa atlanır)."""

    def setUp(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow yok")

    def kaynak(self, dizin, seffaf=True):
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (400, 400), (0, 0, 0, 0) if seffaf else (255, 255, 255, 255))
        d = ImageDraw.Draw(im)
        d.rectangle((100, 40, 300, 200), fill=(237, 28, 36, 255))          # kırmızı simge
        d.rectangle((40, 300, 360, 360), fill=(0, 0, 0, 255))              # siyah yazı
        yol = Path(dizin) / "kaynak.png"
        im.save(yol)
        return yol

    def test_varyantlar_uretilir_siyah_yazi_koyuda_acilir_kirmizi_kalir(self):
        import importlib.util, tempfile
        from PIL import Image
        spec = importlib.util.spec_from_file_location("logo_uret", BASE.parent / "araclar" / "logo_uret.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as t:
            boyut = mod.uret(self.kaynak(t), sembol_alt=250, hedef=Path(t) / "cikti")
            self.assertEqual(set(boyut), {"logo.png", "logo-koyu.png", "logo-sembol.png", "favicon.png"})
            acik = Image.open(Path(t) / "cikti" / "logo.png").convert("RGBA")
            koyu = Image.open(Path(t) / "cikti" / "logo-koyu.png").convert("RGBA")
            sembol = Image.open(Path(t) / "cikti" / "logo-sembol.png").convert("RGBA")
            self.assertEqual(acik.size, koyu.size)
            yazi = (acik.width // 2, acik.height - 20)                       # siyah şerit (alt kısım)
            self.assertEqual(acik.getpixel(yazi)[:3], (0, 0, 0))
            self.assertGreater(min(koyu.getpixel(yazi)[:3]), 200)            # koyu temada açık renk
            kirmizi = (acik.width // 2, 70)
            self.assertEqual(acik.getpixel(kirmizi), koyu.getpixel(kirmizi))  # renkli simge aynen kalır
            self.assertLess(sembol.height, acik.height * 0.7)                # simge varyantı yazıyı içermez
            self.assertEqual(Image.open(Path(t) / "cikti" / "favicon.png").size, (128, 128))

    def test_seffaf_olmayan_kaynak_reddedilir(self):
        import importlib.util, tempfile
        spec = importlib.util.spec_from_file_location("logo_uret", BASE.parent / "araclar" / "logo_uret.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                mod.uret(self.kaynak(t, seffaf=False), hedef=Path(t) / "c")
