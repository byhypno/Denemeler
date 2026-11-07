@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  EROZ VERILERINI YUKLE
echo ============================================================
echo Once Egeser-Cari programinin siyah penceresini KAPATIN. Sonra bir tusa basin.
pause >nul
call :ana > "%~dp0eroz_yukle.txt" 2>&1
set SONUC=%errorlevel%
type "%~dp0eroz_yukle.txt"
echo.
if "%SONUC%"=="0" echo SONUC: BASARILI
if not "%SONUC%"=="0" echo SONUC: BASARISIZ ^(yukaridaki mesaja bakin; eroz_yukle.txt dosyasina da yazildi^)
echo.
echo Pencereyi kapatmak icin bir tusa basin. Sonra programi kisayoldan acin.
pause >nul
exit /b %SONUC%

:ana
if not exist ".venv\Scripts\python.exe" goto kurulu_degil
if exist "ayarlar.bat" call "ayarlar.bat"
echo Guvenlik icin once yedek aliniyor...
".venv\Scripts\python.exe" manage.py yedek_al --hedef "%~dp0veri\yukleme_oncesi_yedek"
if errorlevel 1 goto yedek_hata
echo Veriler yukleniyor...
".venv\Scripts\python.exe" manage.py baslangic_verisi
if errorlevel 1 goto hata
exit /b 0

:kurulu_degil
echo Program kurulu degil. Once kur.bat dosyasini calistirin.
exit /b 1

:yedek_hata
echo Yedek alinamadi; guvenlik icin veri YUKLENMEDI.
exit /b 1

:hata
echo Veri yuklenemedi. Mesaja bakin. Mevcut verilerinize dokunulmadi.
exit /b 1
