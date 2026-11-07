# Windows kurulum rehberi

> **Dürüst not:** Bu betikler Linux'ta yazıldı; içlerindeki Python komutları (şema oluşturma, güncelleme öncesi yedek, sunucu,
> yalnızca yerel dinleme) orada gerçekten çalıştırılarak doğrulandı, ama `.bat` dosyalarının kendisi **Windows'ta henüz denenmedi**.
> İlk kurulumda bir mesajda takılırsanız ekran görüntüsünü paylaşın, düzeltelim.

## 1. Kurulum (bir kez)
1. **Python 3.12 veya üstünü** https://www.python.org adresinden kurun. Kurulum penceresinde **"Add python.exe to PATH"** kutusunu işaretleyin.
2. Proje klasörünü bilgisayara kopyalayın (ör. `C:\CariProgram`). Başka kullanıcıların yazamadığı bir yer seçin.
3. **`kur.bat`** dosyasına çift tıklayın. Sırayla: sanal ortamı kurar, paketleri indirir (internet gerekir), veritabanını hazırlar,
   sizden **yönetici kullanıcı adı ve parola** ister (en az 8 karakter), masaüstüne **Cari Program** kısayolunu koyar.
4. Masaüstündeki **Cari Program** kısayolu programı açar (tarayıcıda `http://127.0.0.1:8000`). Pencereyi kapatınca program kapanır;
   veriler kaybolmaz.

## 1b. Kullanıcılar
`kur.bat` yönetici hesabını oluşturur. Diğer kullanıcılar için (parolayı sorar):
```
.venv\Scripts\python.exe manage.py kullanici_olustur ayse --rol Kasiyer
.venv\Scripts\python.exe manage.py kullanici_olustur mehmet --rol Muhasebe
```
Roller: **Muhasebe**, **Kasiyer** (yalnızca Ofis Kasa), **Görüntüleyici** (salt okunur). Ayrıntı için `README.md`.
Her kullanıcı üst köşedeki adına tıklayarak kendi parolasını değiştirebilir.

## 2. YEDEK AYARI (en önemli adım)
1. Proje klasöründeki **`ayarlar.bat`** dosyasını Not Defteri ile açın.
2. `set CARI_YEDEK_DIZINLERI=` satırını **ayrı bir disk veya USB** yoluyla doldurun. Örnek: `set CARI_YEDEK_DIZINLERI=D:\CariYedek;E:\CariYedek`
   (birden fazla hedef `;` ile ayrılır). **Yedek verinin olduğu diskte olursa disk bozulduğunda ikisi de gider.**
3. **`yedek_gorevi_kur.bat`** dosyasına çift tıklayın: her gün 22:00'de otomatik yedek görevi oluşturur. Bilgisayar o saatte kapalıysa
   yedek alınmaz; bu yüzden programdaki **Yedek** sayfası, son yedek 2 günden eskiyse her sayfanın üstünde kırmızı uyarı gösterir.
4. Programda **Yedek → Şimdi yedek al** ile elle de alabilirsiniz.

Her yedek: veritabanının tutarlı anlık görüntüsünü ve tüm ek dosyaları içeren tek bir `.zip`'tir; hash'lerle doğrulanır ve
**geçici bir klasöre gerçekten geri yüklenerek test edilir**. Son 30 günün hepsi, daha eskiler ayda bir (12 ay) saklanır.

**Güvenlik:** Yedek **şifrelenmez** ve parola özetleriyle tüm mali veriyi içerir. Şifreli bir sürücüye (BitLocker veya VeraCrypt) ya da
şifreli bir bulut klasörüne alın. Gizli anahtar (`secret.key`) yedeğe konmaz.

## 3. Yedekten geri dönme (disk bozulursa / yeni bilgisayara taşırken)
Geri yükleme **çalışan verinin üzerine asla yazmaz**; yeni bir klasöre açar:
```
.venv\Scripts\python.exe manage.py yedek_dogrula D:\CariYedek\cari_yedek_20261106_220000.zip --geri-yukleme-testi
.venv\Scripts\python.exe manage.py yedek_geri_yukle D:\CariYedek\cari_yedek_20261106_220000.zip --hedef C:\CariVeriYeni
```
Sonra `ayarlar.bat` içinde `set CARI_VERI_DIZINI=C:\CariVeriYeni` satırını açın (başındaki `rem`'i silin) ve programı başlatın.
Yeni bilgisayarda önce `kur.bat`, sonra bu adımlar. Kullanıcı parolaları yedekle birlikte gelir.

## 4. Güncelleme
Yeni program dosyalarını aynı klasöre kopyalayın (`veri` klasörüne ve `ayarlar.bat`'a dokunmayın) ve **`kur.bat`'ı tekrar çalıştırın**
(güvenle tekrarlanabilir; yönetici hesabı sorusunu "Ctrl+C" ile geçebilirsiniz). Bekleyen veritabanı güncellemesi varsa program
**önce yedek alır ve doğrular, doğrulanamazsa güncellemeyi uygulamaz.**

## 5. Güvenlik notları
- Program yalnızca bu bilgisayardan (`127.0.0.1`) erişilebilir; ağdaki başka cihazlar bağlanamaz.
- Windows hesabınıza parola koyun, ekranı kilitleyin; diski **BitLocker** ile şifreleyin (Windows Pro).
- Veri klasörü (`veri`): veritabanı + `ekler`. Hepsini yedeğe alın, başkalarıyla paylaşmayın.

## 6. Sorun giderme
| Belirti | Çözüm |
|---|---|
| "Python bulunamadı" | Python'u "Add to PATH" işaretli kurun; yeni bir komut penceresi/`kur.bat` ile tekrar deneyin. |
| "Bu port zaten kullanımda" | Program zaten açıktır (tarayıcıda açılır) ya da başka bir uygulama 8000'i kullanıyor: `ayarlar.bat`'ta `CARI_PORT` değiştirin. |
| Tarayıcı açılmadı | Adres çubuğuna `http://127.0.0.1:8000` yazın. |
| Güncelleme "yedek doğrulanamadı" diyor | Veritabanı değiştirilmedi. Yedek klasörünün yazılabilir ve disk dolu olmadığını kontrol edin. |
| Antivirüs uyarısı | Proje klasörünü antivirüs istisnasına ekleyin (Python betikleri bazen yanlış işaretlenir). |
