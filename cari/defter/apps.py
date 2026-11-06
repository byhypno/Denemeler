from django.apps import AppConfig


class DefterConfig(AppConfig):
    name = "defter"

    def ready(self):
        from . import gunluk
        gunluk.baglan()
