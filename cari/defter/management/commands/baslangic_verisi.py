import json
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from defter import ek_servisi as es
from defter.models import Belge, Cari


class Command(BaseCommand):
    help = ("`baslangic_verisi/` klasöründeki (yukle.json ile tarif edilen) Excel cari takip dosyasını, fiş görsellerini ve cari "
            "dosyalarını ilk kurulumda yükler. Veritabanında zaten cari/belge varsa HİÇBİR ŞEY yapmaz (kurulumu tekrar "
            "çalıştırmak güvenlidir). Klasör yoksa sessizce atlar.")

    def add_arguments(self, parser):
        parser.add_argument("--klasor", default=str(Path(settings.BASE_DIR) / "baslangic_verisi"))

    def _yol(self, klasor: Path, ad: str) -> Path:
        """yukle.json'daki dosya yolu klasörün DIŞINA çıkamaz (../ ile başka dosya okutulmasın)."""
        yol = (klasor / ad).resolve()
        if klasor.resolve() not in yol.parents:
            raise CommandError(f"yukle.json: klasör dışına çıkan yol reddedildi: {ad}")
        if not yol.is_file():
            raise CommandError(f"yukle.json'da adı geçen dosya yok: {ad}")
        return yol

    def handle(self, *args, klasor, **opts):
        klasor = Path(klasor)
        manifest = klasor / "yukle.json"
        if not manifest.is_file():
            self.stdout.write("Başlangıç verisi yok (baslangic_verisi/yukle.json bulunamadı); atlandı.")
            return
        if Cari.objects.exists() or Belge.objects.exists():
            self.stdout.write(self.style.WARNING("Veritabanında zaten cari/belge var; başlangıç verisi YÜKLENMEDİ (mevcut veriye dokunulmaz)."))
            return
        try:
            yukle = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError as e:
            raise CommandError(f"yukle.json okunamadı: {e}")

        if yukle.get("excel"):
            self.stdout.write("Excel cari takip dosyası içe aktarılıyor...")
            call_command("excel_ice_aktar", str(self._yol(klasor, yukle["excel"])), stdout=self.stdout, stderr=self.stderr)
        for k in yukle.get("fis_gorselleri", []):
            self.stdout.write(f"Fiş görselleri ekleniyor: {k['cari']}")
            call_command("fis_gorselleri_ekle", str(self._yol(klasor, k["zip"])), "--cari", k["cari"], stdout=self.stdout, stderr=self.stderr)
        for k in yukle.get("cari_dosyalari", []):
            cari = Cari.objects.filter(unvan=k["cari"]).first()
            if cari is None:
                raise CommandError(f"Cari bulunamadı: {k['cari']}")
            yol = self._yol(klasor, k["dosya"])
            try:
                es.ek_ekle(cari, SimpleUploadedFile(yol.name, yol.read_bytes()), k.get("aciklama", ""), "başlangıç verisi")
                self.stdout.write(f"Cari dosyası eklendi: {yol.name}")
            except es.EkHatasi as e:
                self.stdout.write(self.style.WARNING(f"Cari dosyası eklenemedi ({yol.name}): {e}"))
        self.stdout.write(self.style.SUCCESS("Başlangıç verisi yüklendi."))
