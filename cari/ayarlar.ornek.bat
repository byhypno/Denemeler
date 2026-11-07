@echo off
rem ============================================================================
rem  CARI PROGRAM AYARLARI  (kur.bat bu dosyayi ayarlar.bat olarak kopyalar)
rem  Bu dosyayi Not Defteri ile acip duzenleyebilirsiniz.
rem ============================================================================

rem --- Verilerin (veritabani + ek dosyalar) tutuldugu klasor.
rem     Bos birakirsaniz program klasorundeki "veri" kullanilir.
rem set CARI_VERI_DIZINI=C:\CariVeri

rem --- YEDEK HEDEFLERI (ONEMLI): AYRI bir diske veya USB'ye yonlendirin.
rem     Birden fazla hedef ; ile ayrilir. Ornek:  set CARI_YEDEK_DIZINLERI=D:\CariYedek;E:\CariYedek
rem     Yedek verinin oldugu diskte olursa disk bozuldugunda yedek de kaybolur.
rem     Yedek SIFRELENMEZ: sifreli bir surucuye (BitLocker/VeraCrypt) alin.
set CARI_YEDEK_DIZINLERI=

rem --- HAFTALIK FLASH BELLEK YEDEGI (istege bagli): flash belleginizin harfini yazin. Ornek: set CARI_FLASH_YEDEK=G:\CariYedek
rem     yedek_flash.bat dosyasi bu klasore yedek alir; yedek_gorevi_kur.bat her pazar 22:30 icin otomatik gorev kurar
rem     ^(o saatte flash takili olmali; degilse veri\flash_yedek.log dosyasina not duser^). Harf degisirse buradan guncelleyin.
set CARI_FLASH_YEDEK=

rem --- Program hangi portta calissin (yalnizca bu bilgisayardan erisilir).
set CARI_PORT=8000
