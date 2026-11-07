@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  OTOMATIK YEDEK GOREVLERI
echo ============================================================
call :ana > "%~dp0yedek_kur.txt" 2>&1
set SONUC=%errorlevel%
type "%~dp0yedek_kur.txt"
echo.
if "%SONUC%"=="0" echo SONUC: BASARILI
if not "%SONUC%"=="0" echo SONUC: BASARISIZ ^(yukaridaki mesaja bakin; bu bilgi yedek_kur.txt dosyasina da yazildi^)
echo.
echo Pencereyi kapatmak icin bir tusa basin.
pause >nul
exit /b %SONUC%

:ana
if exist "ayarlar.bat" call "ayarlar.bat"
if "%CARI_YEDEK_DIZINLERI%"=="" goto bos
echo Her gun saat 17:30 icin otomatik yedek gorevi olusturuluyor...
schtasks /create /tn "Cari Program Yedek" /tr "\"%~dp0yedek_al.bat\" sessiz" /sc daily /st 17:30 /f
if errorlevel 1 goto hata
if "%CARI_FLASH_YEDEK%"=="" goto bitir
echo Her cuma 17:45 icin flash bellek yedek gorevi olusturuluyor...
schtasks /create /tn "Cari Program Flash Yedek" /tr "\"%~dp0yedek_flash.bat\" sessiz" /sc weekly /d FRI /st 17:45 /f
if errorlevel 1 goto hata
:bitir
echo Tamam. Gorevler olustu. Bilgisayar o saatte kapaliysa yedek alinmaz;
echo programda Yedek sayfasindan elle de alabilirsiniz.
echo Gorevleri silmek icin: schtasks /delete /tn "Cari Program Yedek" /f
exit /b 0

:bos
echo Once ayarlar.bat dosyasinda CARI_YEDEK_DIZINLERI satirini doldurun.
exit /b 1

:hata
echo Gorev olusturulamadi. Bu dosyaya sag tiklayip "Yonetici olarak calistir" deneyin.
exit /b 1
