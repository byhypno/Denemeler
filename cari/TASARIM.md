# Arayüz tasarım sistemi

**Kimlik: modern panel.** Ferah açık yüzeyler, yumuşak köşeli ve hafif gölgeli kartlar, tek canlı vurgu rengi (indigo),
rakam odaklı gösterge kartları (simge, büyük rakam, mini grafik, "önceki aya göre" değişim), açık sol menü, kişiye göre renklenen avatarlar.
Koyu tema aynı yapının koyu karşılığıdır.

## Dosyalar
| Dosya | Görevi |
|---|---|
| `defter/static/defter/css/cari.css` | Tüm uygulama: token'lar, kabuk, bileşenler, yazdırma |
| `defter/static/defter/css/admin_tema.css` | Yönetim panelini aynı paletle temalar |
| `defter/static/defter/css/fontlar.css`, `fonts/` | Yerel yazı tipleri (SIL OFL; lisanslar `fonts/` içinde) |
| `defter/templates/defter/base.html`, `_ikonlar.html` | Uygulama kabuğu ve SVG simge sprite'ı |
| `defter/static/defter/js/arayuz.js` | Tema düğmesi ve mobil çekmece |
| `defter/trend.py` | Sparkline yolu ve "önceki aya göre" değişim hesabı (saf fonksiyon; `test_trend.py`) |
| `defter/test_arayuz.py` | Kontrast, token tamlığı, çevrimdışılık, erişilebilirlik testleri |

**Çevrimdışı:** hiçbir sayfa dış adrese bağlanmaz (CDN, yazı tipi sunucusu yok); testle korunur.

## Token'lar (üç katman)
1. **Ham değer** yalnızca token bloklarında: `:root` (gündüz), `:root[data-tema="koyu"]` (gece), sistem tercihi için aynı gece paleti.
2. **Anlamlı ad:** `--zemin` (uygulama zemini), `--kart` / `--kart-2` (yüzeyler), `--metin` / `-2` / `-3` (metin kademeleri),
   `--vurgu` (+ `-hover`, `-uzeri`, `-zemin`, `-metin`; birincil eylem, bağlantı, seçili menü), `--pozitif` / `--negatif` / `--uyari` / `--bilgi`
   (+ `-zemin`; durumlar), `--cizgi` / `-guclu` / `-girdi`, `--yan-*` (yan menü), `--g-*` (grafik), `--ipucu-*` (grafik balonu),
   `--av1..8-bg/-fg` (avatar renk çiftleri), `--golge-*` (gölgeler).
3. **Bileşen** yalnızca token kullanır; ham renk yazmak testi kırar.

Ölçek: boşluk `--b-1..7` (4 px tabanı), köşe `--r-kucuk/kontrol/kart/hap`, yazı `--t-xs..2xl` ve `--t-rakam`.
Yazı tipi: **Plus Jakarta Sans** (yerel woff2, SIL OFL; Türkçe karakterler ve ₺ içerir — testle doğrulanır). Rakamları orantılı olduğu için
tablolarda ve göstergelerde `font-variant-numeric: tabular-nums` kullanılır.

## Kontrast (WCAG AA) — testle zorunlu
Metin ≥ 4,5:1 (ana metin ≥ 7:1), metin dışı (form kenarı, odak halkası, grafik) ≥ 3:1; açık ve koyu tema ayrı ayrı denetlenir.
Yeni renk eklerken `test_arayuz.py > CIFTLER` listesine çiftini ekleyin.
**Renk tek başına anlam taşımaz:** eksi tutarda "-" işareti, etiketlerde nokta + metin, değişim etiketinde ok + yüzde + ekran okuyucu metni (`sr-only`) vardır.

## Bileşenler (ad = işlev; görünüş değişse de ad kalır)
`kabuk`/`yan`/`yan-menu` (uygulama iskeleti) · `kart` (yumuşak köşeli kart) · `avatar` + `av-1..8` · `kpi`/`ozet` (gösterge kartları; `kpi-ikon`, `sparkline`, `degisim`, ton sınıfları `ton-vurgu|pozitif|uyari|negatif|bilgi`) · `tablo-kaydir` + `table` (defter tablosu;
`td.sayi` sağa hizalı, `tfoot` üst çizgili toplam) · `form-izgara`, `filtre` · `dugme` / `ikincil` / `kucuk` ·
`chip` + `tamam|uyari|hata|bilgi` (durum; nokta + metin) · `mesaj` (ileti şeridi) · `sekmeler` (segmentli kontrol) · `sayfalama` · `kart bos` (boş durum).
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
