from django.db import migrations


def pasif_yap(apps, schema_editor):
    """Şirket kasası bu programda tutulmayacak; yalnızca Ofis Kasa (küçük ofis harcamaları) kalır.
    Cari Kasa SİLİNMEZ (hareketleri varsa kaybolmasın): pasif yapılır, yönetim panelinden tekrar açılabilir."""
    Hesap = apps.get_model("defter", "Hesap")
    Hesap.objects.filter(ad="Cari Kasa", cari_bagli=True).update(aktif=False)


def geri_al(apps, schema_editor):
    apps.get_model("defter", "Hesap").objects.filter(ad="Cari Kasa", cari_bagli=True).update(aktif=True)


class Migration(migrations.Migration):
    dependencies = [("defter", "0011_gunluk_degistirilemez")]
    operations = [migrations.RunPython(pasif_yap, geri_al)]
