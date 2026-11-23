@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Program kurulu degil. Once kur.bat dosyasini calistirin.
  pause
  exit /b 1
)
if exist "ayarlar.bat" call "ayarlar.bat"
title Egeser-Cari - KAPATMAYIN
set DENEME=0

:basla
".venv\Scripts\python.exe" manage.py sunucu
if not errorlevel 1 goto bitti
set /a DENEME+=1
echo.
echo Program beklenmedik sekilde durdu. Ayrinti: veri\sunucu.log
if %DENEME% GEQ 5 goto hata
echo 5 saniye sonra yeniden baslatiliyor ^(deneme %DENEME%/5^)...
timeout /t 5 /nobreak >nul
goto basla

:hata
echo.
echo Program 5 kez denendi ama calismadi. veri\sunucu.log dosyasini ve bu penceredeki mesaji gonderin.
pause

:bitti

