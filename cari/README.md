# Cari Program (Aşama 1–4)

Tek bilgisayarda, yerelde çalışan cari (tedarikçi) ve **Ofis Kasa** takip programı.
Tutarlar veritabanında **tamsayı kuruş** olarak saklanır; kayıt silinmez, **iptal** edilir.

## Kurulum (Windows)
1. Python 3.11+ kurun (python.org, "Add to PATH" işaretli).
2. Bu klasörde PowerShell açın:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver 127.0.0.1:8000
   ```
3. Tarayıcıda `http://127.0.0.1:8000` açın, oluşturduğunuz kullanıcıyla girin.

Veritabanı, gizli anahtar ve ileride ekler **`veri/`** klasöründe durur (depoya girmez).
Başka konum için: `CARI_VERI_DIZINI` ortam değişkeni.

## Excel'den içe aktarma ve doğrulama
```powershell
python manage.py excel_ice_aktar "C:\yol\Egeser_Tedarikci_Cari_Takip.xlsx"
```
Komut aktarır, sonra her cari için **program bakiyesini Excel'in bakiyesiyle kuruşu kuruşuna karşılaştırır**.
Herhangi bir satırda hata varsa hiçbir şey kaydedilmez. Yeniden aktarmak için `--sifirla`.

## Testler
```powershell
python manage.py test
# Gerçek Excel ile kabul testi:
$env:CARI_EXCEL_YOL="C:\yol\Egeser_Tedarikci_Cari_Takip.xlsx"; python manage.py test defter.tests.GercekExcelKabulTesti
```

## Tutar ve KDV girişi
- Tutarı Türk biçiminde yazın: `1.234,50`. Belirsiz girişler (`1234.50`) kasten reddedilir.
- "KDV girişi": *bilinmiyor* / *girilen tutar KDV hariç* / *girilen tutar KDV dahil*. Oran girilirse matrah, KDV ve (varsa) tevkifat otomatik hesaplanır; **Tutar** alanı kayıtta "ödenecek tutar"a dönüşür.
- Tevkifat yalnızca "KDV hariç" girişte kullanılır.

## Ekranlar (Aşama 2)
Giriş yaptıktan sonra ana sayfa **Genel Bakış**'tır (`http://127.0.0.1:8000`):
- **Göstergeler:** güncel borç, yıllık alış/ödeme/iade, açık mutabakat farkı, kontrol bekleyen kayıt sayısı.
- **Grafikler:** aylık alış/iade/ödeme ve ay sonu bakiye, açık borç yaşlandırması, en borçlu cariler, en çok alınan kalemler. Yıl ve cari filtresi vardır.
- **Kontrol gerektirenler:** ekstre farkı, ay sonu bakiyesi eksiye düşen aylar, aynı tedarikçi evrak numarasının tekrarı, KDV'si girilmemiş alışlar.
- **Ekstre Mutabakatı:** tedarikçi ekstresiyle kayıtlarımızı karşılaştırır; bakiye farkının ne kadarının satırlarla açıklandığını, ne kadarının **açıklanamadığını** gösterir. Yeni mutabakat Yönetim panelinden girilir.
- **Cari ekstresi:** tarih aralığı, dönem başı bakiye, yürüyen bakiye, yazdırma.

Grafikler internet gerektirmez (Chart.js yerel kopya olarak gelir).

**Yaşlandırma varsayımı:** ödeme ve iadeler *en eski borca* mahsup edilir (FIFO), çünkü ödemeler tek tek faturalara bağlanmıyor.
Açık kalemlerin toplamı cari bakiyesine eşittir. "Vadesi geçmiş" yalnızca **vade günü tanımlı** carilerde hesaplanır.

## Kasa (Aşama 3) — iki ayrı kasa
Üst menüde **Kasa**; üstteki sekmelerle kasa değiştirilir. İki hesap hazır gelir (TL):

| Kasa | Cari ile ilişkisi |
|---|---|
| **Ofis Kasa** | **Cari defterinden tamamen bağımsızdır.** Hareketinde cari seçilemez (form alanı yoktur; kod düzeyinde de engellenir). |
| **Cari Kasa** | Cari ödemeleri için ayrı kasa. Hareketinde **cari** ve isteğe bağlı **ilgili cari ödemesi** seçilebilir. Bunlar yalnızca bilgi/referanstır. |

İki kasanın bakiyesi, gün sonu kapanışı ve kilidi birbirinden ayrıdır. **Hiçbir kasa cari bakiyesini, cari ödemesi de hiçbir kasayı otomatik değiştirmez.**
Bir tedarikçiye kasadan nakit öderseniz **iki yere ayrı girersiniz** (cari ödemesi + kasa çıkışı). Biri unutulursa bakiyeler ayrışır:
bunu yakalamak için **Cari Kasa**'da *Cari ödemesi kontrolü* sayfası vardır ("nakit ödendi ama kasadan çıkışı yok" /
"kasadan cariye çıkış var ama cari ödemesi yok"; aynı cari + aynı tutar + en çok 3 gün farkla tek aday varsa *Eşleştir* önerir,
eşleştirme yalnızca referans bağıdır). Ofis Kasa bu kontrolün dışındadır.
Yeni kasa eklemek için Yönetim > Hesaplar; "Cari kasası" kutusu o kasanın cari bağlantılı olup olmadığını belirler.

- **Hızlı giriş:** tarih, yön, tutar (`1.234,50`), kategori, makbuz no, açıklama, isteğe bağlı KDV (Cari Kasa'da ayrıca cari / ilgili ödeme). Kategorileri *Kategoriler* bağlantısından ekleyin.
- **Kasa eksiye düşemez** (Hesap ayarından değiştirilebilir). Bir girişi iptal etmek de kasayı eksiye düşürüyorsa reddedilir.
- **Silme yok, iptal var:** satırdaki iptal kutusuna neden yazılır; iptal kayıtlar bakiyeye girmez, "iptaller: göster" ile görülür.
- **Gün sonu kapanışı:** nakdi sayıp yazarsınız; program kayıtlı bakiyeyle farkı saklar. İsterseniz fark, kapanış gününe
  "Kasa farkı" kategorili bir hareket olarak işlenir. **Kapatılan gün ve öncesi kilitlenir**: o günlere kayıt eklenemez,
  o günlerin kayıtları değiştirilemez/iptal edilemez. Yanlış için güncel tarihli *ters kayıt* girilir.
  (Kilidi kaldırmak yalnızca Yönetim > Gün sonu kapanışları > "Kilitli" kutusundandır; bilinçli ve nadir bir işlemdir.)
- **Kasa dashboard'u:** güncel bakiye, bugün/bu ay giriş-çıkış, aylık giriş/çıkış ve ay sonu bakiye grafiği,
  kategoriye göre çıkışlar, en büyük çıkışlar, kapanış bekleyen günler.

## Ödeme listesi (üst menü: Ödeme Listesi)
Cari ödemeleri için iki liste; ikisi de **Yazdır** (tarayıcıdan PDF'e de kaydedilebilir) ve **Excel'e aktar** ile alınır:
- **Ödenecekler (açık borç):** cari bazında açık borç, yaş dağılımı (0–30 / 31–60 / 61–90 / 90+ gün), en eski belge, vadesi geçmiş tutar
  (yalnızca vade günü tanımlı carilerde). Yazdırmada elle doldurmak için **Planlanan ödeme** ve **Not** kutuları ile imza satırı gelir.
  Toplam, cari bakiyelerinin pozitif toplamına eşittir; ödeme/iadeler en eski borca mahsup edilir (FIFO varsayımı). Fazla ödeme (avans) ayrıca belirtilir.
- **Yapılan ödemeler:** tarih aralığı, cari ve ödeme şekline göre; cari bazında alt toplam, ödeme şekline göre dağılım, genel toplam.

Excel dosyalarında tutarlar kuruşlu sayı olarak yazılır; metin hücreleri (cari adı, açıklama) `=` ile başlasa bile formül olarak çalışmaz.

## Ek dosyalar (Aşama 4, üst menü: Ekler)
Fiş/fatura görseli, ekstre PDF'i, dekont gibi dosyalar **belgeye, kasa hareketine, ekstre mutabakatına veya cari kartına** eklenir.
- **Nereden eklenir:** cari ekstresinde belge satırındaki **📎**, kasada hareket satırındaki **📎**, mutabakat sayfasında **Ekler**,
  cari ekstresinde **Cari dosyaları**. Birden fazla dosya seçilebilir. **Ekler** menüsü tüm dosyaları arama/filtre ile listeler.
- **İzinli türler:** PDF, JPG, PNG, GIF, WEBP, XLSX, DOCX; dosya başına en fazla 20 MB. Uzantıya güvenilmez: dosya **içeriği** türüyle
  uyuşmalıdır (ör. `.pdf` adlı bir PNG reddedilir). HTML/SVG/EXE gibi türler hiç kabul edilmez.
- **Depolama:** `veri/ekler/` klasörü; dosyalar **içerik hash'iyle** adlandırılır (aynı içerik diskte tek kez durur), yalnızca sahibi okuyabilir.
  Dosyalar bir web adresiyle sunulmaz; yalnızca giriş yapmış kullanıcıya özel görünümle verilir.
  **Yedek alırken `veri/` klasörünün tamamını (`cari.sqlite3` + `ekler/`) alın.**
- **Silme yok:** *Kaldır* nedenle işaretler ve listeden çıkarır; dosya diskte kalır.
- **Toplu fiş görseli bağlama** (dosya adı = fiş numarası, ör. `001.png`):
  ```powershell
  python manage.py fis_gorselleri_ekle "C:\yol\Fis_Gorselleri.zip" --cari "ERÖZ HIRDAVAT" --deneme   # önce deneme
  python manage.py fis_gorselleri_ekle "C:\yol\Fis_Gorselleri.zip" --cari "ERÖZ HIRDAVAT"
  ```
  Tekrar çalıştırmak güvenlidir (zaten ekli olanlar atlanır).
- **Depo sağlık kontrolü:** `python manage.py ekleri_dogrula` — eksik dosya, bozuk (hash'i tutmayan) dosya ve kayıtsız dosya var mı?

## Henüz YOK (sonraki aşamalar)
Otomatik yedek, rol/yetki, **işlem günlüğü** (kim ne değiştirdi) ve Windows paketleme (aşama 5).
Fiş OCR (görselden otomatik okuma) yapılmadı; ek dosya deposu yalnızca saklar.
Kasada banka hesabı ve kasa↔banka transferi yoktur (yalnızca Ofis Kasa istendi).
**Şimdilik yedek için `veri/` klasörünü düzenli olarak başka bir diske kopyalayın.**
