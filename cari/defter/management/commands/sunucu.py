import os
import socket
import threading
import webbrowser

from django.core.management.base import BaseCommand, CommandError

from defter import guncelleme, yedek


class Command(BaseCommand):
    help = ("Programı yalnızca BU bilgisayardan erişilebilecek şekilde (127.0.0.1) üretim sunucusuyla (waitress) başlatır, "
            "bekleyen güncellemeleri güvenle uygular ve tarayıcıyı açar.")

    def add_arguments(self, parser):
        parser.add_argument("--port", type=int, default=int(os.environ.get("CARI_PORT", "8000")))
        parser.add_argument("--tarayici-yok", action="store_true")

    def handle(self, *args, port, tarayici_yok, **opts):
        url = f"http://127.0.0.1:{port}/"
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                self.stdout.write(self.style.WARNING(f"Bu port zaten kullanımda; program zaten çalışıyor olabilir: {url}"))
                if not tarayici_yok:
                    webbrowser.open(url)
                return
        try:
            guncelleme.guvenli_migrate(self.stdout.write)
        except yedek.YedekHatasi as e:
            raise CommandError(str(e))
        from django.core.wsgi import get_wsgi_application
        from waitress import serve
        uygulama = get_wsgi_application()
        if not tarayici_yok:
            threading.Timer(1.5, webbrowser.open, args=[url]).start()
        self.stdout.write(self.style.SUCCESS(f"Cari çalışıyor: {url}"))
        self.stdout.write("Kapatmak için bu pencereyi kapatın (Ctrl+C). Veriler kaybolmaz.")
        serve(uygulama, host="127.0.0.1", port=port, threads=4, ident=None)
