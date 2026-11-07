@echo off
setlocal
cd /d "%~dp0"
if exist "ayarlar.bat" call "ayarlar.bat"
if "%CARI_FLASH_YEDEK%"=="" (
  echo ayarlar.bat dosyasinda CARI_FLASH_YEDEK satirini doldurun. Ornek: set CARI_FLASH_YEDEK=G:\CariYedek
  if not "%1"=="sessiz" pause
  exit /b 1
)
if not exist "%CARI_FLASH_YEDEK:~0,3%" (
  echo Flash bellek takili degil ^(%CARI_FLASH_YEDEK:~0,3%^). Takip tekrar calistirin.
  if not exist "veri" mkdir "veri"
  echo %date% %time% Flash yedek ALINAMADI: bellek takili degil >> "veri\flash_yedek.log"
  if not "%1"=="sessiz" pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py yedek_al --hedef "%CARI_FLASH_YEDEK%"
if errorlevel 1 (
  echo FLASH YEDEK ALINAMADI. Mesaja bakin.
  if not exist "veri" mkdir "veri"
  echo %date% %time% Flash yedek BASARISIZ >> "veri\flash_yedek.log"
  if not "%1"=="sessiz" pause
  exit /b 1
)
echo %date% %time% Flash yedek alindi: %CARI_FLASH_YEDEK% >> "veri\flash_yedek.log"
if not "%1"=="sessiz" pause
