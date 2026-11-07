@echo off
setlocal
cd /d "%~dp0"
if exist "ayarlar.bat" call "ayarlar.bat"
if "%CARI_YEDEK_DIZINLERI%"=="" (
  echo Once ayarlar.bat dosyasinda CARI_YEDEK_DIZINLERI satirini doldurun (ayri disk veya USB).
  pause
  exit /b 1
)
echo Her gun saat 17:30 icin otomatik yedek gorevi olusturuluyor...
schtasks /create /tn "Cari Program Yedek" /tr "\"%~dp0yedek_al.bat\" sessiz" /sc daily /st 17:30 /f
if errorlevel 1 (
  echo Gorev olusturulamadi. Bu dosyaya sag tiklayip "Yonetici olarak calistir" deneyin.
  pause
  exit /b 1
)
if not "%CARI_FLASH_YEDEK%"=="" (
  echo Her cuma 17:45 icin flash bellek yedek gorevi olusturuluyor...
  schtasks /create /tn "Cari Program Flash Yedek" /tr "\"%~dp0yedek_flash.bat\" sessiz" /sc weekly /d FRI /st 17:45 /f
  if errorlevel 1 ( echo Flash yedek gorevi olusturulamadi. & pause & exit /b 1 )
)
echo Tamam. Bilgisayar o saatte kapaliysa yedek alinmaz; programda "Yedek" sayfasindan elle de alabilirsiniz.
echo Gorevi silmek icin:  schtasks /delete /tn "Cari Program Yedek" /f
pause
