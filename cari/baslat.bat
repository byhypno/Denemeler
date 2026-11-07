@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Program kurulu degil. Once kur.bat dosyasini calistirin.
  pause
  exit /b 1
)
if exist "ayarlar.bat" call "ayarlar.bat"
title Egeser-Cari
".venv\Scripts\python.exe" manage.py sunucu
if errorlevel 1 (
  echo.
  echo Program baslatilamadi. Yukaridaki mesaja bakin.
  pause
)
