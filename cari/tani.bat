@echo off
setlocal
cd /d "%~dp0"
echo Egeser-Cari tani raporu hazirlaniyor ^(yaklasik 20 saniye surer^)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tani.ps1"
pause
