from django.core.management.base import BaseCommand, CommandError

from defter.ek_servisi import depo_dogrula


class Command(BaseCommand):
    help = "Ek dosya deposunu doğrular: eksik dosya, bozuk (hash tutmayan) dosya ve kayıtsız dosya var mı?"

    def handle(self, *args, **opts):
        s = depo_dogrula()
        self.stdout.write(f"Kayıtlı ek: {s['toplam']}")
        for e in s["eksik"]:
            self.stderr.write(self.style.ERROR(f"EKSİK   #{e.pk} {e.orijinal_ad} -> {e.yol}"))
        for e in s["bozuk"]:
            self.stderr.write(self.style.ERROR(f"BOZUK   #{e.pk} {e.orijinal_ad} -> {e.yol} (içerik hash'i tutmuyor)"))
        for p in s["yetim"]:
            self.stdout.write(self.style.WARNING(f"KAYITSIZ dosya (hiçbir ek kaydı yok): {p}"))
        if s["eksik"] or s["bozuk"]:
            raise CommandError(f"Sorun var: {len(s['eksik'])} eksik, {len(s['bozuk'])} bozuk dosya. Yedekten geri yükleyin.")
        self.stdout.write(self.style.SUCCESS("Depo tutarlı."))
