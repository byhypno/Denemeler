from django.db import migrations


def ac(apps, schema_editor):
    """Ofis Kasa eksiden başlayabilir: çıkış için kasada para olması şart değil."""
    apps.get_model("defter", "Hesap").objects.filter(ad="Ofis Kasa").update(eksiye_dusebilir=True)


class Migration(migrations.Migration):
    dependencies = [("defter", "0019_kasa_harcayan")]
    operations = [migrations.RunPython(ac, migrations.RunPython.noop)]
