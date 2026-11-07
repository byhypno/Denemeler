"""Egeser-Cari Windows kurulum paketini (zip) hazırlar.

Kullanım (Linux/Mac/Windows, internet gerekir; paket hazırlanırken BİR kez):
    python araclar/paket_hazirla.py [--cikti klasor] [--wheels-yok]

Üretilen `Egeser-Cari-Kurulum.zip`: program dosyaları + `wheels/` (Windows için paketler, internetsiz kurulum) + KURULUM.txt.
Hedef bilgisayarda yalnızca zip'i açıp `kur.bat` çalıştırılır. Python yoksa kur.bat winget ile kurmayı dener.
Pakete GİRMEYENLER: gerçek veri (veri/), ayarlar.bat, .venv, testler, __pycache__.
`--baslangic-verisi KLASOR` ile (yukle.json + Excel/zip/pdf) ilk kurulumda yüklenecek verileriniz pakete eklenir.
"""
import argparse
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent                 # cari/
PAKET_ADI = "Egeser-Cari"
HARIC_ON_EKLER = ("veri/", ".venv/", "staticfiles/", "dist/", ".pytest_cache/")
HARIC_AD = {"ayarlar.bat"}

KURULUM_TXT = """EGESER-CARI KURULUMU (Windows 10/11)
=====================================

1) Bu zip dosyasini masaustu gibi KALICI bir yere acin (ornek: C:\\Egeser-Cari).
   Zip'in icinden calistirmayin; once "Tumunu ayikla" deyin. Klasoru sonradan tasimayin
   (masaustu kisayolu eski yeri gosterir; tasirsaniz kur.bat'i yeniden calistirin).

2) "kur.bat" dosyasina cift tiklayin.
   - Python yoksa kendisi kurmayi dener; kurarsa pencereyi kapatip kur.bat'i TEKRAR calistirin.
   - Paketler bu klasorden kurulur, internet gerekmez.
   - Sizden bir YONETICI kullanici adi ve parola ister (en az 8 karakter). Parolayi not edin.

3) Masaustunde logolu "Egeser-Cari" kisayolu olusur. Cift tiklayin: program tarayicida acilir
   (adres: http://127.0.0.1:8000). Siyah pencere simge durumunda calisir; kapatirsaniz program kapanir.

4) YEDEK (onemli): ayarlar.bat dosyasini Not Defteri ile acip CARI_YEDEK_DIZINLERI satirina
   AYRI bir disk/USB yolu yazin (ornek: set CARI_YEDEK_DIZINLERI=E:\\EgeserYedek).
   Sonra yedek_gorevi_kur.bat dosyasina cift tiklayin: her gece otomatik yedek alinir.
   Verileriniz "veri" klasorundedir; programi guncellerken bu klasore dokunmayin.

BASLANGIC VERISI: Bu pakette "baslangic_verisi" klasoru varsa kur.bat verilerinizi (Excel cari takip,
fis gorselleri, cari dosyalari) ilk kurulumda KENDISI yukler. Program bos degilse tekrar yuklemez.

SORUN OLURSA: kur.bat penceresindeki son mesaji fotograflayip gonderin.
"""


def dosyalar():
    """Pakete girecek (cari/ altındaki) göreli yollar. Git varsa izlenen dosyalar; yoksa klasör taranır."""
    try:
        cikti = subprocess.run(["git", "ls-files", "."], cwd=KOK, capture_output=True, text=True, check=True).stdout.split("\n")
        yollar = [Path(p) for p in cikti if p.strip()]
    except (OSError, subprocess.CalledProcessError):
        yollar = [p.relative_to(KOK) for p in KOK.rglob("*") if p.is_file()]
    secilen = []
    for p in yollar:
        s = p.as_posix()
        if (s.startswith(HARIC_ON_EKLER) or "__pycache__" in s or s.endswith(".pyc") or p.name in HARIC_AD
                or p.name.startswith("test") and p.parent.as_posix() == "defter" or s == "defter/tests.py"):
            continue
        if (KOK / p).is_file():
            secilen.append(p)
    return sorted(secilen)


def wheels_indir(hedef: Path):
    """Windows için paketleri indirir (hepsi saf Python tekerleği; python sürümünden bağımsız). tzdata Windows'ta Django için şart:
    pip işaretçileri bu (Linux) makineye göre değerlendirdiğinden açıkça istenir."""
    komut = [sys.executable, "-m", "pip", "download", "-r", str(KOK / "requirements.txt"), "tzdata", "-d", str(hedef),
             "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.12", "--implementation", "cp", "-q"]
    subprocess.run(komut, check=True)


def paket_olustur(cikti_dizin, wheels=True, baslangic_verisi=None) -> Path:
    cikti_dizin = Path(cikti_dizin)
    cikti_dizin.mkdir(parents=True, exist_ok=True)
    zip_yolu = cikti_dizin / (f"{PAKET_ADI}-Kurulum-Veriler-Ile.zip" if baslangic_verisi else f"{PAKET_ADI}-Kurulum.zip")
    with tempfile.TemporaryDirectory() as t, zipfile.ZipFile(zip_yolu, "w", zipfile.ZIP_DEFLATED) as z:
        for p in dosyalar():
            z.write(KOK / p, f"{PAKET_ADI}/{p.as_posix()}")
        z.writestr(zipfile.ZipInfo(f"{PAKET_ADI}/KURULUM.txt", date_time=(2026, 1, 1, 0, 0, 0)),
                   b"\xef\xbb\xbf" + KURULUM_TXT.replace("\n", "\r\n").encode("utf-8"))
        if baslangic_verisi:
            # Kendi verileriniz (Excel, fiş görselleri...) pakete GİRER ama depoya girmez; kur.bat ilk kurulumda yükler.
            kaynak = Path(baslangic_verisi)
            if not (kaynak / "yukle.json").is_file():
                raise SystemExit(f"{kaynak}/yukle.json yok (hangi dosyanın yükleneceğini tarif eden dosya).")
            for f in sorted(p for p in kaynak.rglob("*") if p.is_file()):
                z.write(f, f"{PAKET_ADI}/baslangic_verisi/{f.relative_to(kaynak).as_posix()}")
        if wheels:
            w = Path(t) / "wheels"
            w.mkdir()
            wheels_indir(w)
            for f in sorted(w.glob("*.whl")):
                z.write(f, f"{PAKET_ADI}/wheels/{f.name}")
    return zip_yolu


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cikti", default=str(KOK / "dist"))
    ap.add_argument("--wheels-yok", action="store_true", help="paketleri indirme (yalnızca deneme için)")
    ap.add_argument("--baslangic-verisi", help="yukle.json + veri dosyalarının bulunduğu klasör; ilk kurulumda yüklenir (pakete girer, depoya girmez)")
    a = ap.parse_args()
    yol = paket_olustur(a.cikti, wheels=not a.wheels_yok, baslangic_verisi=a.baslangic_verisi)
    with zipfile.ZipFile(yol) as z:
        print(f"{yol}  ({yol.stat().st_size / 1e6:.1f} MB, {len(z.namelist())} dosya)")
