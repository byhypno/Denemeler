from django.core.management.base import BaseCommand

from defter.roller import rolleri_kur
from defter.yetki import ROL_YETENEKLERI


class Command(BaseCommand):
    help = "Rol gruplarını (Muhasebe, Kasiyer, Görüntüleyici) kurar/onarır. Güvenle tekrar çalıştırılabilir."

    def handle(self, *args, **opts):
        rolleri_kur()
        self.stdout.write(self.style.SUCCESS("Roller hazır: " + ", ".join(ROL_YETENEKLERI)))
