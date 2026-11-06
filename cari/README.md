# Cari Program (Aşama 1)

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

## Kasa
- **Ofis Kasa** (TL) hazır gelir. Kasa hareketleri **cari ödemesinden bağımsızdır**.
- Kasa varsayılan olarak eksiye düşemez (Hesap ayarından değiştirilebilir).
- "İlgili cari ödemesi" alanı yalnızca isteğe bağlı referanstır.

## Henüz YOK (sonraki aşamalar)
Dashboard (aşama 2), gün sonu kapanışı ve kasa kontrol listesi (3), ek dosya/fiş OCR (4),
otomatik yedek, rol/yetki ve işlem günlüğü, Windows paketleme (5).
**Şimdilik yedek için `veri/` klasörünü düzenli olarak başka bir diske kopyalayın.**
