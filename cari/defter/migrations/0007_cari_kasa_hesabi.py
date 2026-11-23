from django.db import migrations


def cari_kasa_olustur(apps, schema_editor):
    Hesap = apps.get_model("defter", "Hesap")
    Hesap.objects.get_or_create(ad="Ofis Kasa", defaults={"tur": "KASA", "cari_bagli": False})
    Hesap.objects.get_or_create(ad="Cari Kasa", defaults={"tur": "KASA", "cari_bagli": True,
                                                          "acilis_bakiye_kurus": 0})


class Migration(migrations.Migration):
    dependencies = [("defter", "0006_cari_kasa_alanlari")]
    operations = [migrations.RunPython(cari_kasa_olustur, migrations.RunPython.noop)]
