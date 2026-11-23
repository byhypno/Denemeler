from django.core.management.base import BaseCommand, CommandError

from defter import yedek


class Command(BaseCommand):
    help = "Bir yedek zip'ini doğrular (hash'ler, veritabanı bütünlüğü); --geri-yukleme-testi ile geçici klasöre geri yükler."

    def add_arguments(self, parser):
        parser.add_argument("zip")
        parser.add_argument("--geri-yukleme-testi", action="store_true")

    def handle(self, *args, zip, geri_yukleme_testi, **opts):
        d = yedek.yedek_dogrula(zip)
        for u in d.uyarilar:
            self.stdout.write(self.style.WARNING("  ! " + u))
        if not d.ok:
            for h in d.hatalar:
                self.stderr.write(self.style.ERROR("  x " + h))
            raise CommandError("Yedek GEÇERSİZ.")
        m = d.manifest
        self.stdout.write(f"Yedek geçerli · oluşturma {m.get('olusturma')} · {len(m.get('dosyalar', {}))} dosya · kayıtlar {m.get('sayilar')}")
        if geri_yukleme_testi:
            t = yedek.geri_yukleme_testi(zip)
            if not t["ok"]:
                for h in t["hatalar"]:
                    self.stderr.write(self.style.ERROR("  x " + h))
                raise CommandError("Geri yükleme testi BAŞARISIZ.")
            self.stdout.write(self.style.SUCCESS(f"Geri yükleme testi geçti · {t['sayilar']}"))
