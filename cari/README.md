# Cari (Aşama 1–5)

Tek bilgisayarda, yerelde çalışan cari (tedarikçi) ve **Ofis Kasa** takip programı.
Tutarlar veritabanında **tamsayı kuruş** olarak saklanır; kayıt silinmez, **iptal** edilir.

## Kurulum (Windows)
1. Python 3.12+ kurun (Django 6 için gerekir) (python.org, "Add to PATH" işaretli).
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
- **Ofis içi göstergeler:** Genel Bakış'ta **Ofis Kasa bakiyesi** (kasa görüntüleme yetkisi olanlara) ve **bu ayın net genel gideri** (girilmediyse "Girilmedi") kartları; tıklayınca ilgili sayfa açılır. Cari filtresinden etkilenmezler ve cari rakamlarına karışmaz.
- **Kontrol gerektirenler:** ekstre farkı, ay sonu bakiyesi eksiye düşen aylar, aynı tedarikçi evrak numarasının tekrarı, KDV'si girilmemiş alışlar.
- **Ekstre Mutabakatı:** tedarikçi ekstresiyle kayıtlarımızı karşılaştırır; bakiye farkının ne kadarının satırlarla açıklandığını, ne kadarının **açıklanamadığını** gösterir. Yeni mutabakat Yönetim panelinden girilir.
- **Cari ekstresi:** tarih aralığı, dönem başı bakiye, yürüyen bakiye, yazdırma.

Grafikler internet gerektirmez (Chart.js yerel kopya olarak gelir).

**Yaşlandırma varsayımı:** ödeme ve iadeler *en eski borca* mahsup edilir (FIFO), çünkü ödemeler tek tek faturalara bağlanmıyor.
Açık kalemlerin toplamı cari bakiyesine eşittir. "Vadesi geçmiş" yalnızca **vade günü tanımlı** carilerde hesaplanır.

## Logo
Egeser logosu programa yerleşiktir (`defter/static/defter/img/`, internet gerekmez): menü ve mobil üst şeritte **simge**, giriş sayfasında **tam logo**
(koyu temada yazısı açık renge çevrilmiş sürüm), yönetim panelinde simge, tarayıcı sekmesinde simge (favicon), **yazdırılan sayfaların** (ekstre, rapor, takvim…) üstünde tam logo.
Logoyu değiştirmek için (şeffaf arka planlı PNG): `pip install pillow` ve `python araclar/logo_uret.py yeni_logo.png`; tüm varyantlar yeniden üretilir.
Simge ile yazı arasındaki satır farklıysa `--sembol-alt-sinir <piksel>` verin.

## Günlük kullanım: giriş, ödeme takvimi, aylık rapor
- **Arayüzden hareket girişi:** Tedarikçi ekstresinde **Yeni alış / Yeni ödeme / Yeni iade** düğmeleri (Yönetici ve Muhasebe). Tedarikçi zaten seçili gelir;
  tür, tarih, evrak no, tutar ve isteğe bağlı KDV girilir. *Kaydet ve yenisini ekle* ile arka arkaya fiş girilir.
  Aynı tedarikçide aynı tür + evrak no ikinci kez girilemez; aynı gün + aynı tür + aynı tutar varsa çift giriş uyarısı çıkar ("yine de kaydet" onayı gerekir).
  Yanlış kayıt silinmez: ekstrede satırdaki **İptal** (neden zorunlu) ile bakiyeden düşer ve işlem günlüğünde kalır. **Fiş kalemleri** (alış fişi/faturası) aynı formdan girilir: açıklama, miktar, birim, birim fiyat, tutar; tutar boşsa miktar × birim fiyat
  hesaplanır, fiş tutarı boşsa kalemlerin toplamı alınır, ikisi farklıysa uyarılır. Ekstrede satırdaki "N kalem" ile açılır; "en çok alınan kalemler" grafiğini besler.
  Açılış/devir girişi ve kayıt düzenleme (kalem düzenleme dahil) hâlâ Yönetim panelindedir.
- **Ödeme takvimi** (menü): açık borçlar **vade tarihine** göre (belge tarihi + carinin vade günü) gruplanır: vadesi geçmiş, bu hafta, 8–30 gün, 30+ gün,
  vadesi tanımsız. Vade günü girilmemiş tedarikçiler gecikmiş sayılmaz, uyarı çıkar. Genel Bakış sayfasında vadesi geçen / bu hafta ödenecek uyarısı görünür.
  Ödemeler en eski borca mahsup edilir (FIFO varsayımı).
- **Veri girişi** (menü): tedarikçi seçip alış/ödeme/iade girme, kasa hareketi, aylık gider ve malzemeler tek sayfada. Yönetim paneli yalnızca seyrek/gelişmiş işler içindir.
- **Kasa kaydını düzenle** (Kasa listesinde "Düzenle"): açıklama, kategori, fiş no ve harcayan düzeltilir; tutar, tarih ve yön değişmez (yanlış tutar için kaydı iptal edip doğrusunu girin). İptal edilmiş ve kapanışı yapılmış güne ait kayıtlar düzeltilemez; her düzeltme işlem günlüğüne yazılır.
- **Kasa raporu** (Kasa → "Rapor"): dönem seçilir (bu ay, önceki ay, son para girişinden bugüne, bu yıl, özel aralık). Ekranda, **Excel** (Kasa defteri: solda girişler, sağda çıkışlar + TOPLAM/KALAN; Özet; Günlük sayfaları) ve **PDF** olarak alınır.
  Kasa hareketindeki **Harcayan** alanı kişi bazında toplam verir; fişi girilmemiş çıkışlar uyarılır. PDF için `reportlab` gerekir (Windows paketinde hazır gelir; Türkçe/₺ yazı tipi `defter/static/defter/fonts/pdf/` içindedir).
- **Aylık rapor** (menü): seçilen ayın tedarikçi hareketleri (ay başı bakiye + alışlar + devir/düzeltme − iadeler − ödemeler = ay sonu bakiye), net genel gider,
  Ofis Kasa harcamaları; önceki aya göre değişim. **Excel** (Özet, Tedarikçiler, Genel gider, Kasa sayfaları) ve **Yazdır / PDF** (tarayıcının "PDF olarak kaydet"i). Varsayılan ay: önceki tam ay.

## Malzemeler (katalog, kategoriler, fiyat hafızası)
Menüde **Malzemeler**. Fiş kalemi girilince açıklama bir **malzemeye** bağlanır; aynı ad (büyük/küçük harf ve aksan farkına bakılmadan) aynı malzemedir ve katalog
kendiliğinden büyür. Mevcut fiş kalemleri geçişle (0018) otomatik gruplandı; **kategoriler tahmin edilmedi**, hazır kategori listesi (Kaynak malzemeleri, El aletleri,
Elektrikli/akülü aletler, Boya ve yapıştırıcı, Vida ve bağlantı elemanları, Elektrik malzemeleri, Sarf malzeme, Diğer) gelir; ekleyip düzenleyebilirsiniz.
- **Liste:** malzeme, kategori, **son alış fiyatı**, önceki fiyat, **değişim (zam kırmızı ▲, indirim yeşil ▼)**, son alış (tarih, tedarikçi). Arama, kategori ve "yalnız zamlılar"
  süzgeci, sıralama (ad, son zam oranı, son alış, toplam tutar). Üstte **son 90 günün zamları**. Kategori tek tek seçilir ya da **listeden seçip toplu atanır**.
- **Malzeme sayfası:** alış fiyatı geçmişi (tablo + tedarikçiye göre çizgi grafik), son/önceki/en düşük/en yüksek/ortalama fiyat, **tedarikçi karşılaştırması** (en ucuz kim),
  düzenleme ve **Birleştir** (aynı malzeme iki adla girildiyse; eski ad bundan sonra birleştiği malzemeye gider, geri alma yok).
- **Fiyat hafızası:** ayrı bir tablo değil, kalemlerden hesaplanır (iptal edilen belgeler sayılmaz). Son fiyat = belge tarihine göre en son alış. Birim fiyat = kalemde girilen
  birim fiyat, yoksa tutar ÷ miktar. Kalem tutarları fişte yazan tutarlardır.
- **Fiş girerken:** kalem açıklamasını katalogdan seçince **son alış fiyatı** (tarih, tedarikçi) görünür, "Son fiyatı kullan" düğmesi vardır; yazdığınız fiyat yüksekse anında **▲ %x zam**
  uyarısı çıkar. Kayıttan sonra her zam için sayfada ayrıca uyarı gösterilir (önceki fiyat ve tarih ile).
- Fiyat karşılaştırması bir önceki alışa göredir (tedarikçi fark etmez); tedarikçiye göre karşılaştırma malzeme sayfasındadır.

## Genel giderler (aylık net gider)
Menüde **Genel giderler**. Şirketin aylık genel giderleri (kira, elektrik, su, mali müşavir, avukat, personel, diğer) her ay **kategori başına tek rakam**
olarak girilir; **personel tüm çalışanlar için tek kalemdir**. Tutarlar **KDV hariç net** girilir (ör. `12.500,00`).
- **Ay girişi:** üstteki ay sekmesinden ayı seçin, tutarları yazıp *Kaydet*. Boş bırakılan satır "gider yok" demektir; kayıtlı bir kalemi boş bırakırsanız 0 olur (silinmez, geçmiş işlem günlüğünde durur).
  *Önceki aydan kopyala* yalnızca bu ayın boş satırlarını doldurur (kira gibi sabit kalemler için). Hatalı satır varsa hiçbiri kaydedilmez.
- **Özet:** seçili ayın net genel gideri (önceki aya göre değişimle), yıl başından birikim, aylık ortalama (gider girilen aylar üzerinden) ve en büyük kalem.
- **Yıllık tablo ve grafik:** kategori × 12 ay, toplamlar; kategoriye göre yığılmış aylık sütun grafiği. **Excel** ve **Yazdır** düğmeleri vardır.
- **Kategoriler:** sayfadan yenisi eklenir; silinmez, kullanılmayacaksa Yönetim > Gider kategorileri'nden pasif yapılır (geçmiş tutarlar tabloda kalır).
- **Yetki:** Yönetici ve Muhasebe girer/düzenler; Görüntüleyici yalnızca görür; Kasiyer göremez.
- Bu giderler **cari defterinden ve kasadan bağımsızdır**; fatura/ekstre ile çift saymamak için yalnızca bir yerden girin.

## Kasa (Aşama 3) — yalnızca ofis içi küçük harcamalar
Üst menüdeki **Kasa**, ofis içi küçük harcamalar (çay, kırtasiye, kargo vb.) içindir; tek hesap **Ofis Kasa**'dır (TL).
**Şirketin asıl kasası ve tedarikçilere yapılan ödemelerin kasası bu programda tutulmaz.** Tedarikçiye yapılan ödeme,
cari ekstresinde **cari ödemesi** olarak girilir (Yönetim > Cari hareketler).

Ofis Kasa **cari defterinden tamamen bağımsızdır** (cari veya cari ödemesi seçilemez). Hiçbir kasa kaydı cari bakiyesini değiştirmez.
*Cari Kasa* ve *Cari ödemesi kontrolü* **kaldırıldı** (geçiş 0015). Daha önce Cari Kasa'ya kayıt girildiyse o kayıtlar silinmez:
hesap pasif kalır, kayıtların açıklamasına "[Tedarikçi: …]" bilgisi yazılır; hiç kaydı yoksa hesap silinir.
Yeni kasa eklemek için Yönetim > Hesaplar.

- **Hızlı giriş:** tarih, yön, tutar (`1.234,50`), kategori, makbuz no, açıklama, isteğe bağlı KDV . Kategorileri *Kategoriler* bağlantısından ekleyin.
- **Kasa eksiye düşemez** (Hesap ayarından değiştirilebilir). Bir girişi iptal etmek de kasayı eksiye düşürüyorsa reddedilir.
- **Silme yok, iptal var:** satırdaki iptal kutusuna neden yazılır; iptal kayıtlar bakiyeye girmez, "iptaller: göster" ile görülür.
- **Gün sonu kapanışı:** nakdi sayıp yazarsınız; program kayıtlı bakiyeyle farkı saklar. İsterseniz fark, kapanış gününe
  "Kasa farkı" kategorili bir hareket olarak işlenir. **Kapatılan gün ve öncesi kilitlenir**: o günlere kayıt eklenemez,
  o günlerin kayıtları değiştirilemez/iptal edilemez. Yanlış için güncel tarihli *ters kayıt* girilir.
  (Kilidi kaldırmak yalnızca Yönetim > Gün sonu kapanışları > "Kilitli" kutusundandır; bilinçli ve nadir bir işlemdir.)
- **Hareket listesinde arama ve süzgeç:** tarih, yön, kategori, **Harcayan** ve metin araması (açıklama / makbuz / harcayan / kategori; büyük-küçük harf ve aksan farkı yok sayılır).
  Listenin altında süzülmüş kayıtların giriş/çıkış/net toplamı (iptaller hariç) görünür; **Bu listeyi Excel'e aktar** aynı süzgeçle dosya verir.
- **Harcayan adlarını düzelt** (Yönetici/Muhasebe/Kasiyer): "ali / Ali / ALİ" gibi yazım farklarını tek adda toplar ya da harcayanı boş kayıtları doldurur.
  Yalnızca ad değişir (tutar/bakiye etkilenmez), her kayıt işlem günlüğüne düşer; **kapanışı yapılmış günlerin kayıtlarına dokunulmaz** (atlanır, sayısı bildirilir).
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

## Arayüz
Yan menülü uygulama kabuğu, açık/koyu tema (yan menü altındaki düğme), mobilde çekmece menü, çizgili "defter" tabloları, rakam şeridi.
Tamamen **çevrimdışı** (yazı tipleri ve simgeler yerel) ve WCAG AA kontrastlı. Ayrıntı: `TASARIM.md`.

## Giriş, roller ve güvenlik (Aşama 5)
- **Giriş:** `/giris/`; üst köşede kullanıcı adınıza tıklayarak **parolanızı değiştirebilir**, **Çıkış**'la oturumu kapatabilirsiniz.
  Aynı kullanıcı adına art arda **5 hatalı denemeden sonra giriş 5 dakika kapanır** (yönetim paneli girişi dahil).
- **Roller** (yöneticiyi `createsuperuser` oluşturur; diğerleri `python manage.py kullanici_olustur ad --rol Muhasebe|Kasiyer|Görüntüleyici` ya da
  Yönetim > Kullanıcılar'da gruba ekleyerek):

  | Rol | Yapabildiği |
  |---|---|
  | **Yönetici** | Her şey + **Yedek**, **Günlük**, kullanıcı yönetimi, kasa ayarları ve **kapanış kilidi kaldırma** |
  | **Muhasebe** | Cari + kasa görüntüleme ve girişi, ek yükleme/kaldırma; yönetim panelinde ekleme/değiştirme (silme yok) |
  | **Kasiyer** | **Yalnızca Ofis Kasa**: hareket girişi/iptali, gün sonu, kasa hareketlerine ek. Cari verileri ve genel giderleri **göremez** |
  | **Görüntüleyici** | Her şeyi **görür**, hiçbir şey yazamaz (düğmeler hiç görünmez) |

  Muhasebe rolü verilince kullanıcı otomatik olarak yönetim paneline girebilir; rol kaldırılınca bu yetki de gider. Rol değişiklikleri günlüğe yazılır.
- **İşlem günlüğü** (Yönetici, üst menü *Günlük*): kim, ne zaman, neyi, eskiden yeniye nasıl değiştirdi; giriş/çıkış ve hatalı denemeler dahil.
  Günlük **eklenir, değiştirilemez, silinemez** (veritabanı tetikleyicileriyle de korunur); parolalar yazılmaz. Her kaydın yönetim sayfasında *Değişiklik geçmişi* bağlantısı vardır.
- **Yedek** (Yönetici): bkz. `README_WINDOWS.md`. Her yedek doğrulanır ve geçici klasöre gerçekten geri yüklenerek denenir; son yedek 2 günden eskiyse her sayfada uyarı çıkar.
- **Windows kurulum:** `kur.bat`, `baslat.bat`, `yedek_gorevi_kur.bat` (bkz. `README_WINDOWS.md`; Windows'ta henüz denenmedi).

## Henüz YOK (sonraki aşamalar)
Fiş OCR (görselden otomatik okuma) yapılmadı; ek dosya deposu yalnızca saklar. Yedek **şifrelenmez** (şifreli sürücü kullanın). Program yalnızca tek bilgisayardan erişilir.
Kasada banka hesabı ve kasa↔banka transferi yoktur (yalnızca Ofis Kasa istendi).
**Şimdilik yedek için `veri/` klasörünü düzenli olarak başka bir diske kopyalayın.**
