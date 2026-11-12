@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if exist "ayarlar.bat" call "ayarlar.bat"
if "%CARI_FLASH_YEDEK%"=="" goto ayarsiz
if not exist "%CARI_FLASH_YEDEK:~0,3%" goto takili_degil
".venv\Scripts\python.exe" manage.py yedek_al --hedef "%CARI_FLASH_YEDEK%"
if errorlevel 1 goto basarisiz
if not exist "veri" mkdir "veri"
echo %date% %time% Flash yedek alindi: %CARI_FLASH_YEDEK% >> "veri\flash_yedek.log"
goto son

:ayarsiz
echo ayarlar.bat dosyasinda CARI_FLASH_YEDEK satirini doldurun. Ornek: set CARI_FLASH_YEDEK=G:\CariYedek
goto hata

:takili_degil
echo Flash bellek takili degil: %CARI_FLASH_YEDEK:~0,3%  Takip bu dosyayi tekrar calistirin.
if not exist "veri" mkdir "veri"
echo %date% %time% Flash yedek ALINAMADI: bellek takili degil >> "veri\flash_yedek.log"
goto hata

:basarisiz
echo FLASH YEDEK ALINAMADI. Yukaridaki mesaja bakin.
if not exist "veri" mkdir "veri"
echo %date% %time% Flash yedek BASARISIZ >> "veri\flash_yedek.log"
goto hata

:hata
if not "%1"=="sessiz" pause
exit /b 1

:son
if not "%1"=="sessiz" pause
exit /b 0
