# Cari Program (Aşama 1 + 2 + 3)

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

## Kasa (Aşama 3)
Üst menüde **Kasa**. Varsayılan hesap **Ofis Kasa** (TL) hazır gelir. Kasa hareketleri **cari ödemesinden bağımsızdır**.
- **Hızlı giriş:** tarih, yön, tutar (`1.234,50`), kategori, isteğe bağlı cari / KDV. Kategorileri *Kategoriler* bağlantısından ekleyin.
- **Kasa eksiye düşemez** (Hesap ayarından değiştirilebilir). Bir girişi iptal etmek de kasayı eksiye düşürüyorsa reddedilir.
- **Silme yok, iptal var:** satırdaki iptal kutusuna neden yazılır; iptal kayıtlar bakiyeye girmez, "iptaller: göster" ile görülür.
- **Gün sonu kapanışı:** nakdi sayıp yazarsınız; program kayıtlı bakiyeyle farkı saklar. İsterseniz fark, kapanış gününe
  "Kasa farkı" kategorili bir hareket olarak işlenir. **Kapatılan gün ve öncesi kilitlenir**: o günlere kayıt eklenemez,
  o günlerin kayıtları değiştirilemez/iptal edilemez. Yanlış için güncel tarihli *ters kayıt* girilir.
  (Kilidi kaldırmak yalnızca Yönetim > Gün sonu kapanışları > "Kilitli" kutusundandır; bilinçli ve nadir bir işlemdir.)
- **Kasa dashboard'u:** güncel bakiye, bugün/bu ay giriş-çıkış, aylık giriş/çıkış ve ay sonu bakiye grafiği,
  kategoriye göre çıkışlar, en büyük çıkışlar, kapanış bekleyen günler.
- **Cari ödemesi kontrolü:** "nakit ödendi ama kasadan çıkışı yok" ve "kasadan cariye çıkış var ama cari ödemesi yok"
  listeleri. Aynı cari + aynı tutar + en çok 3 gün farkla **tek aday** varsa *Eşleştir* önerilir.
  Eşleştirme yalnızca referans bağıdır; hiçbir tutarı değiştirmez.

## Henüz YOK (sonraki aşamalar)
Ek dosya/fiş OCR (4); otomatik yedek, rol/yetki, **işlem günlüğü** (kim ne değiştirdi) ve Windows paketleme (5).
Kasada banka hesabı ve kasa↔banka transferi yoktur (yalnızca Ofis Kasa istendi).
**Şimdilik yedek için `veri/` klasörünü düzenli olarak başka bir diske kopyalayın.**
