# Günlük Google raporu (Egeser Prefabrik + Egeser Konteyner)

Her sabah otomatik çalışır ve iki site için şunları raporlar:

| Bilgi | Kaynak | Ücret |
|---|---|---|
| Google aramada tıklama, gösterim, **ortalama sıra** (gün + 7 gün, değişimle) | Search Console API | Ücretsiz |
| Takip kelimelerinin 7 günlük ortalama sırası ve en çok yükselen/düşen aramalar | Search Console API | Ücretsiz |
| **Google Görseller**: gösterim, tıklama, ortalama sıra, gösterim alan sayfa sayısı, görsel aramalar | Search Console API | Ücretsiz |
| Sitedeki sayfa ve görsel sayısı | Sitemap | Ücretsiz |
| Takip kelimelerinde **bugünkü anlık sıra** (İzmir'den arama) | SerpAPI (isteğe bağlı) | Ücretli |
| Google Görseller'de `site:` aramasında listelenen görsel sayısı | SerpAPI (isteğe bağlı) | Ücretli |

Rapor `seo_rapor/raporlar/` klasörüne HTML olarak kaydedilir, `son.md` en son özeti gösterir,
ayarlanırsa e-posta ile gönderilir. Ham veri `seo_rapor/veri/` klasöründe birikir (geçmiş karşılaştırma).

## Kurulum (bir kerelik, ~15 dakika)

### 1. Search Console'a siteleri ekleyin
<https://search.google.com/search-console> — iki site de ekli ve doğrulanmış olmalı (zaten ekliyse geçin).

### 2. Google Cloud'da service account oluşturun
1. <https://console.cloud.google.com/> → üstten **yeni proje** oluşturun (ör. `egeser-seo`).
2. **APIs & Services → Library** → "**Google Search Console API**" → **Enable**.
3. **IAM & Admin → Service Accounts → Create service account** → ad: `seo-rapor` → Done.
4. Oluşan hesaba tıklayın → **Keys → Add key → Create new key → JSON**. Bir `.json` dosyası iner.
   Bu dosya şifre gibidir, kimseyle paylaşmayın ve depoya eklemeyin.
5. Hesabın e-posta adresini kopyalayın (`seo-rapor@egeser-seo.iam.gserviceaccount.com` gibi).

### 3. Service account'a iki sitede izin verin
Search Console → her site için **Ayarlar → Kullanıcılar ve izinler → Kullanıcı ekle** →
service account e-postası → izin: **Kısıtlı** yeterli.

### 4. GitHub'a gizli anahtarları ekleyin
Depo → **Settings → Secrets and variables → Actions → New repository secret**:

| Ad | Değer | Zorunlu mu |
|---|---|---|
| `GSC_SERVICE_ACCOUNT_JSON` | İnen JSON dosyasının **tüm içeriği** | Evet |
| `SMTP_HOST` | `smtp.gmail.com` | E-posta için |
| `SMTP_PORT` | `465` | E-posta için |
| `SMTP_USER` | Gönderen Gmail adresi | E-posta için |
| `SMTP_PASS` | Gmail **uygulama şifresi** (Google Hesabı → Güvenlik → 2 adımlı doğrulama → Uygulama şifreleri) | E-posta için |
| `RAPOR_ALICI` | Raporun gideceği adres (virgülle birden fazla) | E-posta için |
| `SERPAPI_KEY` | <https://serpapi.com> anahtarı | İsteğe bağlı |

### 5. Çalıştırın
GitHub zamanlanmış işleri yalnızca deponun **varsayılan dalında** çalıştırır; bu dosyalar o dala birleştirilmelidir.
Sonra **Actions → SEO günlük rapor → Run workflow** ile ilk raporu hemen alabilirsiniz.
Bundan sonra her gün 07:17'de kendiliğinden çalışır.

## Ayarlar
`ayarlar.json`:
- `takip_kelimeleri` — sırasını izlemek istediğiniz aramalar. İstediğiniz gibi ekleyin/çıkarın.
- `serpapi.en_fazla_sayfa` — anlık sıra için kaç Google sayfasına bakılacağı (3 = ilk 30 sonuç).
  Her kelime günde en fazla bu kadar SerpAPI araması harcar (iki site aynı aramada bulunur).
  Örnek: 10 kelime × 3 sayfa × 30 gün ≈ 900 arama/ay en kötü durumda; site üst sıralardaysa çok daha az.
- `serpapi.gorsel_sayimi` — görsel sayımı açık/kapalı (site başına günde 1–3 arama).

## Bilmeniz gerekenler
- Search Console verisi **2–3 gün gecikmeli** kesinleşir; rapor her zaman en son kesin günü gösterir.
- "Ortalama sıra" kullanıcılara gerçekten gösterilen konumların ortalamasıdır; konuma ve cihaza göre değişir.
- Google, dizindeki görsellerin **kesin sayısını vermez**. En güvenilir gösterge "Google Görseller'de gösterim
  alan sayfa" ve "görsel gösterimi"dir. SerpAPI `site:` sayısı yaklaşık bir değerdir.
- Google sonuçlarını doğrudan kazımak Google kurallarına aykırıdır ve engellenir; bu yüzden SerpAPI kullanılır.

## Yerelde deneme
```bash
pip install -r seo_rapor/requirements.txt
python seo_rapor/rapor.py --ornek                 # kimlik bilgisi olmadan, uydurma veriyle
GSC_SERVICE_ACCOUNT_JSON="$(cat anahtar.json)" python seo_rapor/rapor.py --eposta-yok
```
