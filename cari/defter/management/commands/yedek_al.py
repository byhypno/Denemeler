from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from defter import yedek


class Command(BaseCommand):
    help = ("Veritabanı + ek dosyaların yedeğini alır, hash'lerle doğrular, geri yükleme testi yapar, eski yedekleri "
            "saklama kuralına göre temizler. Hedefler: --hedef (birden fazla verilebilir) veya CARI_YEDEK_DIZINLERI.")

    def add_arguments(self, parser):
        parser.add_argument("--hedef", action="append", default=None, help="Yedek klasörü (tekrarlanabilir)")
        parser.add_argument("--atla-test", action="store_true", help="Geri yükleme testini atla")
        parser.add_argument("--temizleme", action="store_true", help="Eski yedekleri silme")

    def handle(self, *args, hedef, atla_test, temizleme, **opts):
        try:
            kayitlar = yedek.yedekle([Path(h) for h in hedef] if hedef else None,
                                     test=not atla_test, temizle=not temizleme)
        except yedek.YedekHatasi as e:
            raise CommandError(str(e))
        kotu = 0
        for k in kayitlar:
            satir = f"{k.hedef}: {k.get_durum_display()} {k.dosya} ({k.boyut_bayt // 1024} KB)"
            satir += f" · doğrulandı={'evet' if k.dogrulandi else 'hayır'} · geri yükleme testi={'geçti' if k.geri_yukleme_testi else '—'}"
            if k.durum == "HATA":
                kotu += 1
                self.stderr.write(self.style.ERROR(satir + f"\n   {k.ayrinti}"))
            elif k.durum == "UYARI":
                self.stdout.write(self.style.WARNING(satir + f"\n   {k.ayrinti}"))
            else:
                self.stdout.write(self.style.SUCCESS(satir) + (f"\n   {k.ayrinti}" if k.ayrinti else ""))
        if kotu:
            raise CommandError(f"{kotu} hedefte yedek BAŞARISIZ.")
