from django.core.management.base import BaseCommand, CommandError

from defter import yedek


class Command(BaseCommand):
    help = ("Yedeği YENİ/BOŞ bir veri klasörüne açar. Çalışan verinin üzerine ASLA yazmaz. "
            "Sonra CARI_VERI_DIZINI'ni bu klasöre yönlendirin.")

    def add_arguments(self, parser):
        parser.add_argument("zip")
        parser.add_argument("--hedef", required=True, help="Yeni (boş) veri klasörü")

    def handle(self, *args, zip, hedef, **opts):
        try:
            s = yedek.geri_yukle(zip, hedef)
        except yedek.YedekHatasi as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(f"Geri yüklendi: {s['hedef']}"))
        self.stdout.write("Kullanmak için:  set CARI_VERI_DIZINI=" + str(s["hedef"]) +
                          "   (kalıcı yapmak için başlatıcıdaki ayarı değiştirin)")
