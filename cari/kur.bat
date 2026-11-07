@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  EGESER-CARI KURULUMU  (guvenle tekrar calistirilabilir)
echo ============================================================

where python >nul 2>nul
if errorlevel 1 goto python_yok
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul
if errorlevel 1 goto python_yok
goto python_tamam

:python_yok
echo Python 3.12 veya uzeri bulunamadi ya da calismiyor.
echo ^(Windows "Microsoft Store" Python kisayolu varsa o calismaz; gercek Python gerekir.^)
where winget >nul 2>nul
if errorlevel 1 goto python_elle
echo winget ile Python 3.12 kuruluyor ^(internet gerekir, birkac dakika surer^)...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto python_elle
echo.
echo Python kuruldu. Bu pencereyi KAPATIN ve kur.bat dosyasini TEKRAR calistirin.
pause
exit /b 0

:python_elle
echo https://www.python.org adresinden Python 3.12 veya uzerini kurun.
echo Kurulumda "Add python.exe to PATH" kutusunu ISARETLEYIN, sonra kur.bat dosyasini tekrar calistirin.
pause
exit /b 1

:python_tamam

if not exist ".venv\Scripts\python.exe" (
  echo Sanal ortam olusturuluyor...
  python -m venv .venv
  if errorlevel 1 ( echo Sanal ortam olusturulamadi. & pause & exit /b 1 )
)

if exist "wheels\*.whl" (
  echo Gerekli paketler yerel klasorden kuruluyor ^(internet gerekmez^)...
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links=wheels -r requirements.txt
) else (
  echo Gerekli paketler kuruluyor ^(internet gerekir^)...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
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

if exist "baslangic_verisi\yukle.json" (
  echo Baslangic verileri yukleniyor ^(Excel, fis gorselleri^)...
  ".venv\Scripts\python.exe" manage.py baslangic_verisi
  if errorlevel 1 echo Baslangic verisi yuklenemedi; mesaja bakin. Kurulum devam ediyor.
)

echo Egeser-Cari kisayolu ^(logolu simgeyle^) masaustune ve Baslat menusune olusturuluyor...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kisayol_olustur.ps1"
if errorlevel 1 echo Kisayol olusturulamadi; programi baslat.bat dosyasina cift tiklayarak da acabilirsiniz.

echo.
echo ============================================================
echo  KURULUM TAMAM. Masaustundeki "Egeser-Cari" kisayoluyla acin.
echo  ONEMLI: ayarlar.bat dosyasinda CARI_YEDEK_DIZINLERI satirini
echo  (ayri disk/USB) doldurun, sonra yedek_gorevi_kur.bat calistirin.
echo ============================================================
pause
