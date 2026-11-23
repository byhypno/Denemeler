from django.core.management.base import BaseCommand, CommandError

from defter import guncelleme, yedek


class Command(BaseCommand):
    help = "Bekleyen veritabanı güncellemelerini uygular; veritabanı doluysa ÖNCE yedek alıp doğrular."

    def handle(self, *args, **opts):
        try:
            s = guncelleme.guvenli_migrate(self.stdout.write)
        except yedek.YedekHatasi as e:
            raise CommandError(str(e))
        if not s["uygulanan"]:
            self.stdout.write("Veritabanı güncel.")
