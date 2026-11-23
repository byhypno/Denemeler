import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from defter import ek_servisi as es
from defter import gunluk, metin
from defter.fields import kurus_bicimle
from defter.models import Belge, Cari


class Command(BaseCommand):
    help = ("`baslangic_verisi/` klasöründeki (yukle.json ile tarif edilen) Excel cari takip dosyasını, fiş görsellerini ve cari "
            "dosyalarını ilk kurulumda yükler. Veritabanında zaten belge varsa HİÇBİR ŞEY yapmaz (yalnız elle girilmiş tedarikçi/kasa kayıtları engel değildir) (kurulumu tekrar "
            "çalıştırmak güvenlidir). Klasör yoksa sessizce atlar.")

    def add_arguments(self, parser):
        parser.add_argument("--klasor", default=str(Path(settings.BASE_DIR) / "baslangic_verisi"))

    def _yol(self, klasor: Path, ad: str) -> Path:
        """yukle.json'daki dosya yolu klasörün DIŞINA çıkamaz (../ ile başka dosya okutulmasın)."""
        yol = (klasor / ad).resolve()
        if klasor.resolve() not in yol.parents:
            raise CommandError(f"yukle.json: klasör dışına çıkan yol reddedildi: {ad}")
        if not yol.is_file():
            raise CommandError(f"yukle.json'da adı geçen dosya yok: {ad}")
        return yol

    def handle(self, *args, klasor, **opts):
        klasor = Path(klasor)
        manifest = klasor / "yukle.json"
        if not manifest.is_file():
            self.stdout.write("Başlangıç verisi yok (baslangic_verisi/yukle.json bulunamadı); atlandı.")
            return
        try:
            yukle = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError as e:
            raise CommandError(f"yukle.json okunamadı: {e}")

        yapilan = 0
        excel_yuklendi = False
        if yukle.get("excel"):
            if Belge.objects.exists():
                self.stdout.write(self.style.WARNING("Veritabanında zaten belge (alış/ödeme) kaydı var; Excel cari takip dosyası YÜKLENMEDİ (mevcut veriye dokunulmaz)."))
            else:
                self.stdout.write("Excel cari takip dosyası içe aktarılıyor...")
                call_command("excel_ice_aktar", str(self._yol(klasor, yukle["excel"])), stdout=self.stdout, stderr=self.stderr)
                excel_yuklendi = yapilan = 1
        if excel_yuklendi:
            for k in yukle.get("fis_gorselleri", []):
                self.stdout.write(f"Fiş görselleri ekleniyor: {k['cari']}")
                call_command("fis_gorselleri_ekle", str(self._yol(klasor, k["zip"])), "--cari", k["cari"], stdout=self.stdout, stderr=self.stderr)
        for k in yukle.get("hareketler", []):
            yapilan += self._hareketler(klasor, k)
        for k in yukle.get("cari_dosyalari", []):
            cari = Cari.objects.filter(unvan=k["cari"]).first()
            if cari is None:
                raise CommandError(f"Cari bulunamadı: {k['cari']}")
            yol = self._yol(klasor, k["dosya"])
            if cari.ekler.filter(orijinal_ad=yol.name).exists():
                self.stdout.write(f"Cari dosyası zaten ekli, atlandı: {yol.name}")
                continue
            try:
                es.ek_ekle(cari, SimpleUploadedFile(yol.name, yol.read_bytes()), k.get("aciklama", ""), "başlangıç verisi")
                self.stdout.write(f"Cari dosyası eklendi: {yol.name}")
                yapilan = 1
            except es.EkHatasi as e:
                self.stdout.write(self.style.WARNING(f"Cari dosyası eklenemedi ({yol.name}): {e}"))
        if yapilan:
            self.stdout.write(self.style.SUCCESS("Başlangıç verisi yüklendi."))
        else:
            self.stdout.write("Yüklenecek yeni başlangıç verisi yok (hepsi zaten yüklü).")
        self.stdout.write("Programdaki tedarikçiler:")
        for c in Cari.objects.order_by("unvan"):
            self.stdout.write(f"  - {c.unvan}: {c.belgeler.filter(iptal=False).count()} hareket, bakiye {kurus_bicimle(c.bakiye_kurus())} TL")

    @staticmethod
    def _cari_bul(unvan):
        hedef = metin.katla(unvan)
        return next((c for c in Cari.objects.all() if metin.katla(c.unvan) == hedef), None)

    @staticmethod
    def _acilis_mi(b) -> bool:
        return b.tur == Belge.Tur.ACILIS or (b.tur == Belge.Tur.DUZELTME_EKSI and b.aciklama.startswith("Açılış bakiyesi"))

    @transaction.atomic
    def _hareketler(self, klasor: Path, k: dict) -> int:
        """Ekstreden çıkarılmış hareket listesini (JSON) tedarikçiye işler. Bakiye beklenenle eşleşmezse HİÇBİR ŞEY kaydedilmez.
        Tedarikçinin zaten (açılış dışı) hareketi varsa dokunulmaz. `mevcut_acilisi_iptal_et` true ise, tedarikçide yalnızca
        açılış bakiyesi kayıtları varsa onlar iptal edilir (silinmez; neden yazılır) ve ayrıntılı hareketler yüklenir."""
        veri = json.loads(self._yol(klasor, k["dosya"]).read_text(encoding="utf-8"))
        unvan = veri["cari"]
        cari = self._cari_bul(unvan)
        iptal_edilen = 0
        if cari is not None:
            aktif = list(cari.belgeler.filter(iptal=False))
            if aktif:
                if veri.get("mevcut_acilisi_iptal_et") and all(self._acilis_mi(b) for b in aktif):
                    pass                                   # aşağıda iptal edilir
                else:
                    self.stdout.write(self.style.WARNING(f"{unvan}: zaten hareketi var; ekstre hareketleri YÜKLENMEDİ."))
                    return 0
        with gunluk.sessiz(f"Başlangıç verisi: {unvan} ekstre hareketleri") as g:
            if cari is None:
                cari = Cari.objects.create(unvan=unvan)
            elif cari.belgeler.filter(iptal=False).exists():
                for b in cari.belgeler.filter(iptal=False):
                    b.iptal, b.iptal_nedeni = True, "Ayrıntılı ekstre hareketleri yüklendi (açılış bakiyesi yerine)"
                    b.save()
                    iptal_edilen += 1
            if veri.get("cari_notu") and not cari.not_metni:
                cari.not_metni = veri["cari_notu"]
                cari.save(update_fields=["not_metni"])
            ac = veri.get("acilis")
            if ac and ac.get("tutar_kurus"):
                alacak = ac.get("yon") == "ALACAK"
                Belge.objects.create(cari=cari, tur=Belge.Tur.DUZELTME_EKSI if alacak else Belge.Tur.ACILIS, tarih=date.fromisoformat(ac["tarih"]),
                                     tutar_kurus=ac["tutar_kurus"], aciklama=ac.get("aciklama", "Açılış bakiyesi"), kaynak_notu=veri.get("kaynak", ""))
            for r in veri["satirlar"]:
                Belge.objects.create(cari=cari, tur=r["tur"], tarih=date.fromisoformat(r["tarih"]), tutar_kurus=r["tutar_kurus"],
                                     harici_evrak_no=r.get("evrak_no", ""), aciklama=r.get("aciklama", ""),
                                     odeme_sekli=r.get("odeme_sekli", ""), kaynak_notu=veri.get("kaynak", ""))
            bak = cari.bakiye_kurus()
            if bak != veri["beklenen_bakiye_kurus"]:
                raise CommandError(f"{unvan}: bakiye {kurus_bicimle(bak)} TL, ekstrede {kurus_bicimle(veri['beklenen_bakiye_kurus'])} TL (eşleşmedi; hiçbir şey kaydedilmedi).")
            g["metin"] = (f"Başlangıç verisi: {unvan} · {len(veri['satirlar'])} hareket, bakiye {kurus_bicimle(bak)} TL"
                          + (f" · {iptal_edilen} açılış kaydı iptal edildi" if iptal_edilen else ""))
        self.stdout.write(f"{unvan}: {len(veri['satirlar'])} hareket yüklendi · bakiye {kurus_bicimle(bak)} TL - EŞLEŞTİ"
                          + (f" · önceki {iptal_edilen} açılış kaydı iptal edildi" if iptal_edilen else ""))
        return 1
