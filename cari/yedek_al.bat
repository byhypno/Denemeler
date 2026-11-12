@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if exist "ayarlar.bat" call "ayarlar.bat"
".venv\Scripts\python.exe" manage.py yedek_al
if errorlevel 1 (
  echo YEDEK ALINAMADI. Mesaja bakin.
  if not "%1"=="sessiz" pause
  exit /b 1
)
if not "%1"=="sessiz" pause
