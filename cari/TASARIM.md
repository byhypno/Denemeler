# Arayüz tasarım sistemi

**Kimlik: kolonlu muhasebe defteri.** Soluk adaçayı kâğıt, defter yeşili mürekkep, rakam sütunları, başlık altında ve toplamlarda **çift çizgi**.
Dolap kartlarından oluşan genel bir "panel" görünümü yerine, bir defterin düzeni: rakamlar tek bir çizgili şeritte, tablolar defter gibi.

## Dosyalar
| Dosya | Görevi |
|---|---|
| `defter/static/defter/css/cari.css` | Tüm uygulama: token'lar, kabuk, bileşenler, yazdırma |
| `defter/static/defter/css/admin_tema.css` | Yönetim panelini aynı paletle temalar |
| `defter/static/defter/css/fontlar.css`, `fonts/` | Yerel yazı tipleri (SIL OFL; lisanslar `fonts/` içinde) |
| `defter/templates/defter/base.html`, `_ikonlar.html` | Uygulama kabuğu ve SVG simge sprite'ı |
| `defter/static/defter/js/arayuz.js` | Tema düğmesi ve mobil çekmece (başka JS yok) |
| `defter/test_arayuz.py` | Kontrast, token tamlığı, çevrimdışılık, erişilebilirlik testleri |

**Çevrimdışı:** hiçbir sayfa dış adrese bağlanmaz (CDN, yazı tipi sunucusu yok); testle korunur.

## Token'lar (üç katman)
1. **Ham değer** yalnızca token bloklarında: `:root` (gündüz), `:root[data-tema="koyu"]` (gece), sistem tercihi için aynı gece paleti.
2. **Anlamlı ad:** `--kagit` (zemin), `--sayfa` (yüzey), `--murekkep` / `-2` / `-3` (metin kademeleri), `--yesil` (birincil eylem, bağlantı),
   `--kirmizi` (eksi/hata), `--amber` (uyarı), `--mavi` (bilgi), `--cizgi` / `-guclu` / `-girdi` (çizgiler), `--yan-*` (yan menü), `--g-*` (grafik).
3. **Bileşen** yalnızca token kullanır; ham renk yazmak testi kırar.

Ölçek: boşluk `--b-1..7` (4 px tabanı), köşe `--r-kucuk/kontrol/panel/hap` (kademeli, tek bir yarıçap değil),
yazı `--t-xs..2xl` ve `--t-rakam`. Yazı tipleri: **IBM Plex Sans** (arayüz ve tablolar; rakamları doğuştan sabit genişlikte)
ve **Barlow Semi Condensed** (başlıklar ve büyük rakamlar; `tabular-nums` ile).

## Kontrast (WCAG AA) — testle zorunlu
Metin ≥ 4,5:1 (ana metin ≥ 7:1), metin dışı (form kenarı, odak halkası, grafik) ≥ 3:1; açık ve koyu tema ayrı ayrı denetlenir.
Yeni renk eklerken `test_arayuz.py > CIFTLER` listesine çiftini ekleyin.
**Renk tek başına anlam taşımaz:** eksi tutarda "-" işareti, etiketlerde simge + metin vardır.

## Bileşenler (ad = işlev; görünüş değişse de ad kalır)
`kabuk`/`yan`/`yan-menu` (uygulama iskeleti) · `kart` (panel) · `kpi`/`ozet` (rakam şeridi) · `tablo-kaydir` + `table` (defter tablosu;
`td.sayi` sağa hizalı, `tfoot` çift çizgili toplam) · `form-izgara`, `filtre` · `dugme` / `ikincil` / `kucuk` ·
`chip` + `tamam|uyari|hata|bilgi` (durum; simgeyi CSS getirir) · `mesaj` (ileti şeridi) · `sekmeler` · `sayfalama` · `kart bos` (boş durum).
Simge: `{% ikon "ad" %}` (dekoratif, `aria-hidden`; anlamı yanındaki metin taşır).

## Erişilebilirlik kuralları
`lang="tr"`, "İçeriğe geç" bağlantısı, `main#icerik`, adlandırılmış `nav`, seçili sayfada `aria-current="page"`,
görünür klavye odağı (`:focus-visible`), 44 px dokunma hedefi (mobil), `prefers-reduced-motion` ve `prefers-color-scheme` saygısı,
hata iletisi `role="alert"`, başarı `role="status"`, görsel önizlemelerde `alt`.

## Tema
Düğme (yan menü altı) açık ↔ koyu geçer; seçim tarayıcıda (`cari_tema`) saklanır, sayfa çizilmeden önce uygulanır (yanıp sönme yok),
grafikler yeni renklerle yeniden çizilir, yönetim paneli de aynı temayı kullanır. Seçim yoksa sistem tercihi izlenir.

## Değişiklik süreci
Önce token'ı/bileşeni burada ve `cari.css`'te değiştirin, sonra şablonda kullanın. Şablonda satır içi `style=` ve ham renk kullanmayın.
Yeni bir görünüm gerekiyorsa mevcut bir bileşenin varyantı mı, yoksa gerçekten yeni bir bileşen mi olduğuna (amaç ve davranış aynı mı?) bakın.
