# Cari Program — Mimari ve Yol Haritası Raporu

Hedef: **tek bilgisayarda** çalışan, **dashboard/analiz ekranlı** kendi cari (tedarikçi/müşteri hesap takip) programımız.
Kaynak: `Egeser_Calisma_Paketi` (Hareketler, Fiş Kalemleri, Tedarikçiler, Ekstre Mutabakatı yapısı) + sistem tasarımı/ADR çerçevesi.
Güven düzeyleri: [Kesin] / [Muhtemel] / [Tahmin].

---

## GÜNCELLEME 2 (son karar): Paraşüt bağlantısı YOK, KASA modülü VAR

Kullanıcı kararı: program Paraşüt ile **hiçbir bağlantı kurmayacak**; bağımsız çalışacak. Ayrıca **kasa** ayrı bir bölüm olarak tutulacak.
Bu nedenle aşağıdaki "GÜNCELLEME" bölümündeki Paraşüt maddeleri (salt okunur senkron, API, üçlü mutabakat) **geçersizdir**; KDV, çok kullanıcı ve OCR kararları geçerlidir.

### Bu karardan doğan sonuçlar
- Program artık **kendi başına asıl kayıt** (yönetim kaydı) olur. Yedek, işlem günlüğü ve test **daha da kritik**. [Kesin]
- Paraşüt'e de giren veriler iki yerde elle girilecekse **çift emek ve ayrışma riski** vardır; kullanıcı bunu bilerek kabul etti. Azaltmak için: Excel/CSV içe aktarma serbest, dışa aktarma (mali müşavire Excel/PDF) hazır olsun. [Kesin]
- Mutabakat ekranı yalnızca **tedarikçi ekstresi ↔ bizim kayıt** olarak kalır.
- Resmi muhasebe yazılımı olmadığı uyarısı geçerli: bu program yönetim kaydıdır.

### Kasa modülü (ayrı bölüm)
**Ne için:** nakit giriş/çıkışı, gün sonu kasa kontrolü, harcama kategorileri, nakit akışı.

**Veri modeli (ek tablolar):**
| Tablo | Ana alanlar |
|---|---|
| `Hesap` | ad, tür (kasa / banka-opsiyonel), para birimi, açılış bakiyesi (kuruş), aktif |
| `KasaHareketi` | hesap→, tarih, yön (giriş/çıkış), tutar_kuruş, kategori→, cari→ (opsiyonel), belge→ (opsiyonel), makbuz/fiş no, açıklama, ek dosya |
| `Kategori` | ad, tür (gelir/gider), genel gider grubu (opsiyonel) |
| `GunSonu` | hesap→, tarih, beklenen bakiye, sayılan tutar, fark, not, kilitli_mi |
| `Transfer` | kaynak hesap→, hedef hesap→, tutar, tarih (kasa↔banka) |

**Kritik kural: tek kayıt, iki etki.** Tedarikçiye nakit ödeme yapıldığında bu **tek işlem** hem cari bakiyeyi azaltır hem kasadan çıkış olur. Ödemeyi cari tarafına ve kasa tarafına ayrı ayrı girmek çift sayım yaratır. [Kesin]

**Diğer kurallar:**
- Kasa bakiyesi **eksiye düşemez** (uyarı veya engel; ayardan seçilir).
- **Gün sonu kapanışı:** sayım ↔ hesaplanan bakiye farkı kaydedilir; kapatılan günün kayıtları kilitlenir, düzeltme ancak ters kayıtla yapılır.
- Kategorili gider girişi KDV alanlarını (matrah/oran/tevkifat) destekler; ileride genel gider raporu bu veriden çıkar.
- Makbuz/fiş görseli yüklenebilir, OCR akışı (onaylı taslak) kasa fişlerinde de çalışır.

**Kasa dashboard'u:** güncel kasa bakiyesi, bugünkü giriş/çıkış, aylık nakit akışı (giriş-çıkış-bakiye), kategori dağılımı, en büyük çıkışlar, gün sonu farkları, açık (kapatılmamış) günler.

### Güncel yol haritası
| Aşama | İçerik |
|---|---|
| 0 | Kalan soruların cevabı (aşağıda) |
| 1 | Şema (cari + belge + KDV/tevkifat + hesap/kasa), Excel içe aktarma, bakiye doğrulama testi |
| 2 | Cari dashboard + ekstre mutabakatı |
| 3 | **Kasa modülü:** hareket, gün sonu, transfer, kasa dashboard'u |
| 4 | Ek dosya deposu + fiş OCR (onaylı taslak) |
| 5 | Giriş/rol, otomatik yedek, geri yükleme testi, Windows paketleme |
| 6 | (İsteğe bağlı) çok kullanıcı, genel gider raporu, PDF ekstre |

### Kalan sorular (kasa için)
1. Kasa sadece **TL** mi, döviz kasası da var mı?
2. **Banka hesabı** da takip edilsin mi, yoksa sadece nakit kasa mı?
3. Kasayı kim kullanıyor, **yetki** ayrımı gerekiyor mu (örn. giriş yapabilen / sadece görebilen)?
4. Kasa ile cari ödemesi aynı ekrandan mı yapılsın? (Önerim: evet, tek işlem iki etki.)

---

## GÜNCELLEME (kullanıcı cevapları sonrası)

**Cevaplar:** Windows · yalnızca tedarikçi carisi · ileride çok kullanıcı "olabilir" · KDV seçenekleri olmalı · fiş OCR isteniyor · **işletme zaten Paraşüt kullanıyor.**

### (GEÇERSİZ — bkz. Güncelleme 2) Ana karar: Paraşüt'ün yerine değil, yanında
- **Paraşüt = resmi kayıt** (e-fatura, KDV, beyanname altyapısı, mali müşavir erişimi). Biz onu **taklit etmeyiz.** [Kesin]
- **Bizim program = yerel arşiv + analiz + mutabakat katmanı:** fiş görselleri ve belge deposu, tedarikçi ekstre mutabakatı, Paraşüt'te olmayan analizler, fiş OCR.
- **Çift giriş yasak:** Aynı fatura hem Paraşüt'e hem buraya elle girilmemeli. Çözüm: Paraşüt'ten **salt okunur** senkron (API) veya dışa aktarılmış dosyadan içe aktarma; elle girişi sadece Paraşüt'e girmeyen kayıtlar (fiş, ekstre notu, düzeltme) için yap.
- **Kontrol ekranı:** "Paraşüt bakiyesi ↔ bizim bakiye ↔ tedarikçi ekstresi" üçlü karşılaştırma. Farklar burada görünür.
- Paraşüt API (v4, OAuth2; cari ve alış faturası uç noktaları) var gibi görünüyor, ama bunu **üçüncü taraf kaynaklardan** gördüm; resmi dokümanla (apidocs.parasut.com) ve planının API iznini doğrulamak gerekir. [Muhtemel]
- Bu yüzden önce **Paraşüt'ten alınan dışa aktarma dosyalarıyla** başla, API'yi sonraya bırak.

### Çok kullanıcı "olabilir" → şimdiden alınacak önlem
- Django kalıyor; tüm sorgular ORM üzerinden, SQLite'a özgü numara yok (PostgreSQL'e geçiş açık kalır).
- Şimdilik 127.0.0.1. İleride aynı PC "sunucu" olur: ağ erişimi, kullanıcı rolleri ve parola zorunlu hale gelir. Şimdiden kullanıcı/rol tablosu ve işlem günlüğü kurulur.

### KDV modeli (belge ve kalem düzeyinde)
- Alanlar: matrah, KDV oranı, KDV tutarı, **tevkifat oranı** (işletmede KDV tevkifatı var), toplam; "tutar KDV dahil/hariç" seçeneği; kuruş yuvarlama kuralı tek yerde.
- KDV oranları **ayar tablosundan** yönetilir (kodda sabit yok): mevzuat değişince kod değişmez.
- Fişlerde KDV basılı değilse belge "KDV bilinmiyor" işaretlenir; tutarın hariç olduğu varsayımı açıkça belirtilir.

### Fiş OCR (evet) — tasarım
1. Fiş görseli yüklenir → Claude görsel okuma → **taslak kalemler** üretilir (otomatik kaydedilmez).
2. **Doğrulama zorunlu:** kalem toplamı ↔ fişteki el yazısı toplam karşılaştırılır; uyuşmazsa kırmızı uyarı. Kullanıcı onaylamadan kayıt oluşmaz. (Mevcut çalışmada aynı yöntem 10/10 tuttu.)
3. **Gizlilik:** görseller internete (API'ye) gider. Açık onay ayarı, API anahtarı dosyada değil güvenli depoda, kişisel veri/plaka içeren görseller için uyarı. [Kesin]
4. Yerel OCR (Tesseract vb.) el yazısında zayıf kalır; bu yüzden bulut tabanlı model öneriyoruz. [Muhtemel]

### Güncel yol haritası
| Aşama | İçerik |
|---|---|
| 0 | Paraşüt'ten hangi dışa aktarma/API erişimi var kontrol et |
| 1 | Şema (KDV/tevkifat dahil), Excel + Paraşüt dosyası içe aktarma, bakiye doğrulama |
| 2 | Dashboard + üçlü mutabakat ekranı |
| 3 | Ek dosya deposu + fiş OCR (onaylı taslak akışı) |
| 4 | Yedek, giriş, paketleme |
| 5 | (İsteğe bağlı) Paraşüt API senkronu, çok kullanıcı |

---

## 0. Önce söylenmesi gerekenler (risk ve uyarılar)

1. **Bu program resmi muhasebe yazılımı değildir.** e-Fatura/e-Defter/beyanname üretmez; yönetim amaçlı cari takiptir. Resmi kayıt mali müşavirde kalır. [Kesin]
2. **Tek bilgisayar = tek hata noktası.** Disk bozulursa veya fidye yazılımı girerse her şey gider. Yedekleme tasarımın *parçasıdır*, sonradan eklenecek bir şey değil. [Kesin]
3. **Para tutarı asla `float` ile tutulmamalı.** Mevcut Excel'de bazı bakiyelerde `…1099999999` türü kayan nokta artıkları görülüyor; bu aynı sorunun işareti. Tutarlar tamsayı kuruş (veya `Decimal`) olarak saklanmalı. [Kesin]
4. **Bakiye saklanmaz, hesaplanır.** Hareketler silinmez/ezilmez; hata düzeltmesi "düzeltme satırı" ile yapılır (Excel'de zaten böyle planlanmıştı). Bu, denetlenebilirliği korur. [Kesin]
5. **"Yap mı, satın al mı?"** Hazır programlar (Logo, Mikro, Paraşüt, Odoo/ERPNext) var. Kendi programımızın gerekçesi: sadece cari + özel analiz, ucuz, tam kontrol, Excel'den kolay geçiş. Gerekçe "daha ucuz/özel" değilse hazır ürün daha az risklidir. [Muhtemel]
6. **Veri hassas** (bakiyeler, vergi ve ceza kayıtları). Varsayılan: internete çıkmayan, şifreli disk, yerel çalışma. KVKK açısından kişi/araç plakası verisi de içerir. [Kesin]

---

## 1. Gereksinimler

**İşlevsel (Excel çalışmasından çıkan):**
- Cari kartı (tedarikçi, ileride müşteri): ünvan, vergi no, iletişim, vade/not.
- Belgeler: alış faturası/fiş, iade, ödeme, dekont, düzeltme.
- Belge kalemleri (fişteki satırlar: ürün, adet, birim fiyat, KDV durumu).
- Bakiye ve ekstre: cari bazlı borç/alacak/bakiye, tarih aralığı.
- **Ekstre mutabakatı:** tedarikçi ekstresiyle bizim kayıt farkı, fark nedeni, durum.
- Ek dosyalar: fiş görseli, PDF ekstre, dekont (belgeye bağlı).
- İçe aktarma: mevcut Excel'den bir kerelik göç.
- Dışa aktarma: Excel/PDF ekstre, yazdırılabilir cari ekstresi.
- **Dashboard/analiz** (bölüm 6).

**İşlevsel olmayan:**
- Tek kullanıcı (en fazla 2–3 kişi aynı PC'de), çevrimdışı çalışabilir.
- Veri hacmi küçük: yılda yaklaşık binler satır. Performans sorunu yok. [Muhtemel]
- Türkçe arayüz, TL biçimi (`1.234.567,89 ₺`), Türkçe sıralama/arama (İ/ı sorunu).
- Kolay kurulum: çift tıkla açılan kısayol; "terminal" yok.
- Geri alınabilirlik: yedek, geri yükleme testi, işlem günlüğü (kim/ne zaman değiştirdi).

**Kısıtlar (varsayımlar, doğrula):** Windows PC, tek geliştirici + Claude, bütçe düşük, resmi entegrasyon yok. [Tahmin — bölüm 10 soruları]

---

## 2. Mimari seçenekler

| | A. Streamlit + SQLite | B. Django + SQLite (web, yerelde) | C. FastAPI + SQLite + özel arayüz | D. Masaüstü (Qt/PySide) | E. Excel/Access'te kalmak |
|---|---|---|---|---|---|
| Kurulum zorluğu | Çok kolay | Kolay-orta | Orta | Orta-zor | En kolay |
| Veri girişi (form, tablo) | Zayıf-orta | **Çok iyi (admin hazır)** | Elle yazılır | İyi | İyi (alışıldık) |
| Dashboard/grafik | **Çok iyi** | İyi (Chart.js/Plotly) | İyi | Orta | Orta |
| Veri bütünlüğü / kısıtlar | Elle | **Güçlü (ORM, migration, validasyon)** | Orta | Orta | Zayıf |
| Yetki/giriş | Elle | **Hazır** | Elle | Elle | Zayıf |
| Paketleme (tek .exe) | Zor | Orta | Orta | Orta | Gerekmez |
| İleride mobil/web | Zor | Kolay | **En kolay** | Zor | Yok |
| Claude ile geliştirme hızı | Hızlı | Hızlı | Orta | Yavaş (test zor) | — |

**Öneri [Muhtemel]: B — Django + SQLite**, dashboard için Chart.js (veya Plotly) ile.
Gerekçe: cari programın ağırlığı veri girişi, bütünlük ve ekstredir; Django bunları (CRUD ekranları, doğrulama, göç, kullanıcı girişi, Türkçe yerelleştirme) hazır verir. Dashboard hafif bir ek katmandır.

**Alternatif:** Önce **A (Streamlit)** ile 1–2 günde prototip yapıp işleyişi test etmek, sonra Django'ya geçmek mantıklıdır. Streamlit veri girişinde hızla sınırlarına gelir, bu yüzden kalıcı çözüm saymam.

**Neden masaüstü (Qt) değil?** Yerleşik mimari avantajı var ama bu ortamda arayüzü görsel test edemem. Web arayüzünü tarayıcıyla ben doğrulayabilirim. [Kesin]

---

## 3. Önerilen mimari (yüksek seviye)

```
┌──────────────── Tek Windows PC ─────────────────┐
│  Tarayıcı  ──http://127.0.0.1:8000──►  Django   │
│  (Chrome/Edge)                         uygulama │
│                                            │    │
│                       ┌────────────────────┤    │
│                       ▼                    ▼    │
│                SQLite (cari.db)     ekler/ klasörü
│                WAL modu             (fiş, PDF)  │
│                       │                    │    │
│                       └──► Günlük yedek ◄──┘    │
│                            (2. disk / USB /     │
│                             şifreli bulut)      │
└─────────────────────────────────────────────────┘
```

- **Sunucu sadece 127.0.0.1'e bağlanır** (ağdan erişilemez). [Kesin]
- Açılış: masaüstü kısayolu → arka planda sunucu → tarayıcı otomatik açılır.
- Paketleme: önce `.bat` kısayolu; olgunlaşınca PyInstaller ile tek klasörlük kurulum.

---

## 4. Veritabanı

**SQLite** (tek dosya, kurulum yok, bu ölçek için fazlasıyla yeterli). [Kesin]
- `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, düzenli `VACUUM`/bütünlük kontrolü.
- Ne zaman PostgreSQL? Birden fazla bilgisayardan eşzamanlı kullanım gerekirse. Django ile geçiş mümkündür, bu yüzden Django seçimi geleceği de korur.

**Önerilen şema (özet):**

| Tablo | Ana alanlar |
|---|---|
| `Cari` | id, tür (tedarikçi/müşteri), ünvan, vergi_no, telefon, not, aktif |
| `Belge` | id, cari→, tür (alış/iade/ödeme/düzeltme), evrak_no, tarih, vade, tutar_kuruş, kdv_durumu, açıklama, iptal_mi |
| `BelgeKalem` | belge→, sıra, ürün, adet, birim_fiyat_kuruş, tutar_kuruş |
| `Hareket` (veya Belge'den türetilmiş) | cari→, tarih, yön (borç/alacak), tutar_kuruş, belge→ |
| `Ek` | belge→, dosya_yolu, sha256, tür, yüklenme_tarihi |
| `EkstreMutabakat` | cari→, ekstre_tarihi, ekstre_bakiye_kuruş, bizim_bakiye_kuruş, fark_kuruş, durum, açıklama |
| `IslemGunlugu` | kullanıcı, zaman, tablo, kayıt_id, eski/yeni değer (JSON) |
| `Ayar` | para birimi, ofis payı oranı vb. |

Kurallar:
- Belge türünün borca etkisi **tablo/kural ile** belirlenir (Excel'deki gizli "Listeler" sayfasının karşılığı): alış → borcu artırır, ödeme/iade → azaltır.
- Silme yok: `iptal_mi` bayrağı + günlük kaydı.
- Aynı `(cari, evrak_no, tür)` için tekilleştirme kısıtı: çift giriş engellenir.

---

## 5. Depolama ve yedekleme

- **Veri:** `C:\CariProgram\veri\cari.db`. **Ekler:** `...\ekler\YYYY\MM\<sha256>.jpg|pdf`. Görselleri veritabanına gömme; DB'de yol + hash tut. [Kesin]
- **Yedek (3-2-1 kuralı):** 3 kopya, 2 farklı ortam, 1 tanesi bilgisayar dışında.
  - Her kapanışta/günlük otomatik: SQLite `backup` API'si ile tutarlı kopya + `ekler/` klasörü → zip, tarih damgalı.
  - Hedefler: ikinci disk veya USB + (isteğe bağlı) **şifreli** bulut klasörü.
  - Saklama: son 30 günlük, son 12 aylık.
  - **Aylık geri yükleme testi** (yedekten açıp bakiyeyi kontrol et). Test edilmemiş yedek yedek değildir. [Kesin]
- **Disk şifreleme:** Windows BitLocker (Pro sürümde) veya VeraCrypt kasası.

---

## 6. Dashboard ve analiz ekranı

**Üst KPI kartları:** toplam borç (tedarikçilere), toplam alacak (müşterilerden), ay içi alış, ay içi ödeme, vadesi geçmiş tutar, açık mutabakat farkı.

**Grafikler:**
1. Aylık alış / iade / ödeme + ay sonu bakiye çizgisi (karışık grafik).
2. **Vade yaşlandırma (aging):** 0–30, 31–60, 61–90, 90+ gün (borç/alacak).
3. En çok borçlu olunan / en çok alacaklı olunan 10 cari (yatay çubuk).
4. Cari bazlı bakiye trendi (cari seçilince).
5. Ürün/kalem bazlı harcama (fiş kalemlerinden: en çok alınan ürünler).
6. Ödeme takvimi / yaklaşan vadeler listesi.

**Tablolar:** hareket listesi (filtre: cari, tarih, tür), ekstre mutabakat farkları, "kontrol gerektiren" kayıtlar (eksi bakiye dönemleri, tekrar eden evrak no, ekstre farkı).

**Yazdır/aktar:** cari ekstresi PDF, hareketler Excel.

**Tasarım ilkeleri:** KPI en üstte, renk tutarlı (borç kırmızı, alacak yeşil değil: renk körlüğü için işaret + metin de kullan), TL biçimi tek yerde tanımlı.

---

## 7. Güvenlik

- 127.0.0.1'e bağlan, kullanıcı girişi (parola hash'li), oturum zaman aşımı.
- Windows hesabı parolalı, ekran kilidi, BitLocker.
- Bağımlılıkları sabitle (`requirements.txt` sürüm kilidi), güncelleme takvimi.
- Günlük (audit log): kim/ne zaman/neyi değiştirdi.
- Gizli bilgi (API anahtarı vb.) dosyada değil, ortam değişkeni/Windows kimlik deposunda.
- Fiş OCR için Claude API kullanılırsa görsel **internete gider**: bunu isteğe bağlı, açık onaylı bir özellik yap; ticari gizlilik ve KVKK'yı değerlendir. [Kesin]

---

## 8. Test ve doğruluk (en önemli kısım)

- **Kabul testi 1:** Excel'den içe aktarılan verinin hesapladığı güncel bakiye, mevcut Excel Panel bakiyesiyle **kuruşu kuruşuna** eşleşmeli.
- **Kabul testi 2:** Ekstre mutabakat farkı Excel'deki farkla eşleşmeli.
- Birim testleri: bakiye hesabı, iade/ödeme işareti, vade yaşlandırma sınırları, yuvarlama.
- Mevcut veri bütünlüğü bulguları (devir teyidi, eksi bakiyeli aylar) yeni sistemde "kontrol listesi" ekranı olarak görünmeli.
- Skill'ler: `engineering:testing-strategy`, `data:validate-data`, `security-review`, `engineering:code-review`.

---

## 9. Yol haritası

| Aşama | İçerik | Çıktı |
|---|---|---|
| **0. Karar** (1 gün) | Bölüm 10 soruları, ADR | Seçilen stack |
| **1. Çekirdek** | Şema, cari/belge/kalem CRUD, bakiye hesabı, Excel içe aktarma, kabul testi 1 | Çalışan veri girişi + doğru bakiye |
| **2. Dashboard** | KPI, aylık grafik, aging, top cariler, filtre | Analiz ekranı |
| **3. Mutabakat + ekler** | Ekstre farkı ekranı, fiş/PDF yükleme, işlem günlüğü | Denetlenebilir kayıt |
| **4. Güvenlik/Yedek/Paket** | Giriş, otomatik yedek, geri yükleme testi, kurulum paketi | Günlük kullanıma hazır |
| **5. Genişleme** | Müşteri carisi, genel gider/vergi modülü, PDF ekstre, OCR (isteğe bağlı) | — |

Tahmini efor (Claude ile): aşama 1–2 yaklaşık birkaç günlük yoğun çalışma, 3–4 bir o kadar. [Tahmin]

---

## 10. Kararı netleştirecek sorular

1. İşletim sistemi Windows mu? (Sürüm: Pro mu Home mu? BitLocker için önemli.)
2. Sadece **tedarikçi** carisi mi, **müşteri** carisi de var mı?
3. Birden fazla kullanıcı/bilgisayar ileride gerekecek mi? (Gerekecekse mimari değişir.)
4. KDV detayı gerekli mi (matrah/KDV ayrı), yoksa tutar yeterli mi? Döviz var mı?
5. Vade ve ödeme planı takibi istiyor musun?
6. Fiş görselinden otomatik okuma (OCR) ister misin, veriyi internete göndermeye razı mısın?
7. Genel gider/vergi takibi aynı programa girsin mi, ayrı mı kalsın?

---

## 11. İlgili skill'ler ve GitHub repoları

**Bu çalışmada kullanılabilecek skill'ler:**
`engineering:system-design`, `engineering:architecture` (ADR), `data:build-dashboard`, `data:sql-queries`, `data:validate-data`,
`engineering:testing-strategy`, `engineering:code-review`, `security-review`, `design-skills:design-systems`, `design-skills:ux-writing` (Türkçe arayüz metinleri),
`anthropic-skills:xlsx`, `anthropic-skills:pdf` (içe/dışa aktarma), `engineering:deploy-checklist`, `engineering:documentation`.

**Repolar (hafızadan, bu oturumda doğrulanmadı — kullanmadan önce lisans ve aktiflik kontrol edilmeli):**
- `django/django` — web çatısı, admin, ORM
- `jazzband/django-import-export` — Excel/CSV içe/dışa aktarma
- `chartjs/Chart.js` ve `apache/echarts` — dashboard grafikleri
- `plotly/plotly.py` — Python tarafında grafik alternatifi
- `Kozea/WeasyPrint` — HTML'den PDF (ekstre çıktısı)
- `pyinstaller/pyinstaller` — Windows için paketleme
- `streamlit/streamlit` — hızlı prototip
- Referans/ilham (kopyalamak için değil): `odoo/odoo`, `frappe/erpnext`, `akaunting/akaunting`, `beancount/beancount` (çift taraflı defter mantığı için)

---

## 12. Sonuç — tek cümlede

**Django + SQLite + Chart.js**, yerelde (127.0.0.1) çalışan, tutarları kuruş olarak saklayan, silmeyen (düzeltme satırlı), otomatik yedekli bir cari program kuralım; ilk hedef: mevcut Excel'i içe aktarıp **bakiyeyi kuruşu kuruşuna** doğrulamak.
