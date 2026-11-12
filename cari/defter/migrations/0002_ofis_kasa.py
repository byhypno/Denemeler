from django.db import migrations


def ofis_kasa_olustur(apps, schema_editor):
    Hesap = apps.get_model("defter", "Hesap")
    Hesap.objects.get_or_create(ad="Ofis Kasa", defaults={"tur": "KASA", "acilis_bakiye_kurus": 0})


class Migration(migrations.Migration):
    dependencies = [("defter", "0001_initial")]
    operations = [migrations.RunPython(ofis_kasa_olustur, migrations.RunPython.noop)]
