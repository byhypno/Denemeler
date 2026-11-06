from django.core.management.base import BaseCommand, CommandError

from defter.excel_aktar import excel_beklenen_bakiyeler, ice_aktar
from defter.fields import kurus_bicimle
from defter.models import Cari


class Command(BaseCommand):
    help = "Excel cari takip dosyasını içe aktarır ve bakiyeleri Excel'dekiyle karşılaştırır."

    def add_arguments(self, parser):
        parser.add_argument("yol", help="Egeser_Tedarikci_Cari_Takip.xlsx yolu")
        parser.add_argument("--sifirla", action="store_true",
                            help="Mevcut cari/belge/kalem kayıtlarını silip yeniden aktar")

    def handle(self, *args, yol, sifirla, **opts):
        try:
            ozet = ice_aktar(yol, sifirla=sifirla)
        except (RuntimeError, ValueError, FileNotFoundError) as e:
            raise CommandError(str(e))
        if ozet["hatalar"]:
            self.stderr.write(self.style.ERROR("HATALAR (hiçbir şey kaydedilmedi):"))
            for h in ozet["hatalar"]:
                self.stderr.write("  - " + h)
            raise CommandError("İçe aktarma geri alındı.")
        self.stdout.write(f"Cari: {ozet['cari']}  Belge: {ozet['belge']}  Kalem: {ozet['kalem']}  "
                          f"Mutabakat satırı: {ozet['mutabakat_satiri']}")
        for u in ozet["uyarilar"]:
            self.stdout.write(self.style.WARNING("  ! " + u))

        self.stdout.write("\nBakiye doğrulaması (program ↔ Excel):")
        beklenen = excel_beklenen_bakiyeler(yol)
        tamam = True
        for unvan, bek in beklenen.items():
            cari = Cari.objects.filter(unvan=unvan).first()
            hes = cari.bakiye_kurus() if cari else None
            ok = hes == bek
            tamam &= ok
            durum = self.style.SUCCESS("EŞLEŞTİ") if ok else self.style.ERROR("FARKLI")
            self.stdout.write(f"  {unvan}: program {kurus_bicimle(hes)} ₺ · Excel {kurus_bicimle(bek)} ₺ → {durum}")
        if not tamam:
            raise CommandError("Bakiyeler Excel ile eşleşmiyor!")
