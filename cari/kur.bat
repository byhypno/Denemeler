@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  CARI PROGRAM KURULUMU  (guvenle tekrar calistirilabilir)
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo Python bulunamadi. https://www.python.org adresinden Python 3.12 veya uzerini kurun.
  echo Kurulumda "Add python.exe to PATH" kutusunu ISARETLEYIN, sonra bu dosyayi tekrar calistirin.
  pause
  exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"
if errorlevel 1 (
  echo Python 3.12 veya uzeri gerekli (Django 6).
  python --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam olusturuluyor...
  python -m venv .venv
  if errorlevel 1 ( echo Sanal ortam olusturulamadi. & pause & exit /b 1 )
)

echo Gerekli paketler kuruluyor (internet gerekir)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo Paketler kurulamadi. Internet baglantisini kontrol edin. & pause & exit /b 1 )

if not exist "ayarlar.bat" copy "ayarlar.ornek.bat" "ayarlar.bat" >nul
call "ayarlar.bat"

echo Veritabani hazirlaniyor...
".venv\Scripts\python.exe" manage.py veritabani_guncelle
if errorlevel 1 ( echo Veritabani hazirlanamadi. Mesaja bakin. & pause & exit /b 1 )

".venv\Scripts\python.exe" manage.py shell -c "import sys; from django.contrib.auth import get_user_model as g; sys.exit(0 if g().objects.filter(is_superuser=True).exists() else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo YONETICI HESABI: kullanici adi ve parola belirleyin ^(parola en az 8 karakter^).
  ".venv\Scripts\python.exe" manage.py createsuperuser
) else (
  echo Yonetici hesabi zaten var, olusturma atlandi.
)

echo Masaustu kisayolu olusturuluyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Cari.lnk'); $s.TargetPath='%~dp0baslat.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()"

echo.
echo ============================================================
echo  KURULUM TAMAM. Masaustundeki "Cari" kisayoluyla acin.
echo  ONEMLI: ayarlar.bat dosyasinda CARI_YEDEK_DIZINLERI satirini
echo  (ayri disk/USB) doldurun, sonra yedek_gorevi_kur.bat calistirin.
echo ============================================================
pause
