import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from defter.roller import rolleri_kur
from defter.yetki import ROL_YETENEKLERI


class Command(BaseCommand):
    help = "Rol atanmış yeni kullanıcı oluşturur. Yönetici için 'createsuperuser' kullanın."

    def add_arguments(self, parser):
        parser.add_argument("kullanici")
        parser.add_argument("--rol", required=True, choices=list(ROL_YETENEKLERI))
        parser.add_argument("--parola", help="Verilmezse güvenli biçimde sorulur")

    def handle(self, *args, kullanici, rol, parola, **opts):
        User = get_user_model()
        if User.objects.filter(username=kullanici).exists():
            raise CommandError(f"'{kullanici}' kullanıcısı zaten var.")
        if not parola:
            parola = getpass.getpass("Parola: ")
            if parola != getpass.getpass("Parola (tekrar): "):
                raise CommandError("Parolalar uyuşmuyor.")
        try:
            validate_password(parola)
        except ValidationError as e:
            raise CommandError(" ".join(e.messages))
        rolleri_kur()
        u = User.objects.create_user(kullanici, password=parola)
        u.groups.add(Group.objects.get(name=rol))
        self.stdout.write(self.style.SUCCESS(f"'{kullanici}' oluşturuldu · rol: {rol}"))
