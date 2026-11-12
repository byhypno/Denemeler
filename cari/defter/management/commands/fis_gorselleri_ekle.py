import os
import zipfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from defter import ek_servisi as es
from defter.models import Belge, Cari


class Command(BaseCommand):
    help = ("Bir zip dosyasındaki (veya klasördeki) fiş görsellerini, dosya adındaki fiş numarasıyla eşleşen "
            "cari belgelerine ek olarak bağlar. Örnek: 001.png -> evrak no '001'. Tekrar çalıştırmak güvenlidir.")

    def add_arguments(self, parser):
        parser.add_argument("yol", help="zip dosyası veya görsel klasörü")
        parser.add_argument("--cari", required=True, help="Cari ünvanı (tam)")
        parser.add_argument("--aciklama", default="Fiş görseli")
        parser.add_argument("--deneme", action="store_true", help="Hiçbir şey kaydetmeden eşleşmeleri göster")

    def _dosyalar(self, yol: Path):
        """(ad, bayt) üretir. Zip içeriği diske AÇILMAZ; yol bileşenleri ve boyut sınırı denetlenir."""
        if yol.is_dir():
            for p in sorted(yol.iterdir()):
                if p.is_file() and p.stat().st_size <= settings.EK_MAX_BAYT:
                    yield p.name, p.read_bytes()
        elif zipfile.is_zipfile(yol):
            with zipfile.ZipFile(yol) as z:
                bilgiler = [i for i in z.infolist() if not i.is_dir()]
                if sum(i.file_size for i in bilgiler) > 1024 ** 3:
                    raise CommandError("Zip toplam boyutu 1 GB sınırını aşıyor.")
                for i in sorted(bilgiler, key=lambda i: i.filename):
                    if i.file_size > settings.EK_MAX_BAYT:
                        yield i.filename, None
                    else:
                        yield i.filename, z.read(i)
        else:
            raise CommandError("Yol bir zip dosyası veya klasör olmalı.")

    def handle(self, *args, yol, cari, aciklama, deneme, **opts):
        yol = Path(yol)
        if not yol.exists():
            raise CommandError(f"Bulunamadı: {yol}")
        try:
            c = Cari.objects.get(unvan=cari)
        except Cari.DoesNotExist:
            raise CommandError(f"Cari bulunamadı: '{cari}'")
        sayac = {"eklendi": 0, "zaten": 0, "eslesmedi": 0, "hata": 0}
        for ad, veri in self._dosyalar(yol):
            govde = os.path.splitext(es.temiz_ad(ad))[0]
            belge = (Belge.objects.filter(cari=c, evrak_no=govde, iptal=False).first()
                     or (Belge.objects.filter(cari=c, evrak_no=govde.zfill(3), iptal=False).first()
                         if govde.isdigit() else None))
            if belge is None:
                sayac["eslesmedi"] += 1
                self.stdout.write(self.style.WARNING(f"  eşleşmedi : {ad}"))
                continue
            if veri is None:
                sayac["hata"] += 1
                self.stderr.write(self.style.ERROR(f"  çok büyük : {ad}"))
                continue
            if deneme:
                sayac["eklendi"] += 1
                self.stdout.write(f"  eklenecek : {ad} -> {belge}")
                continue
            try:
                es.ek_ekle(belge, SimpleUploadedFile(es.temiz_ad(ad), veri), aciklama, "toplu aktarım")
                sayac["eklendi"] += 1
            except es.EkHatasi as e:
                if "zaten ekli" in str(e):
                    sayac["zaten"] += 1
                else:
                    sayac["hata"] += 1
                    self.stderr.write(self.style.ERROR(f"  hata      : {e}"))
        self.stdout.write(
            f"{'[DENEME] ' if deneme else ''}Eklendi: {sayac['eklendi']} · zaten ekli: {sayac['zaten']} · "
            f"eşleşmedi: {sayac['eslesmedi']} · hata: {sayac['hata']}")
        if sayac["hata"]:
            raise CommandError("Bazı dosyalar eklenemedi.")
