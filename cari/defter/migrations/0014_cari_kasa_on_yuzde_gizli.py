from django.db import migrations, models


def cari_kasayi_gizle(apps, schema_editor):
    """Cari Kasa bakiyesi hep eksi olacağından ön yüzde gösterilmez; kayıtlar arkada (yönetim panelinde) durur."""
    apps.get_model("defter", "Hesap").objects.filter(ad="Cari Kasa", cari_bagli=True).update(on_yuzde_gizli=True)


class Migration(migrations.Migration):
    dependencies = [("defter", "0013_cari_kasa_sadece_cikis")]
    operations = [
        migrations.AddField(model_name="hesap", name="on_yuzde_gizli", field=models.BooleanField(
            default=False, verbose_name="Ön yüzde gizle",
            help_text="İşaretliyse bu kasa Kasa sayfasında, sekmelerde ve kontrol ekranında görünmez; kayıtlar arkada durur ve yalnızca Yönetim panelinden girilir/görülür.")),
        migrations.RunPython(cari_kasayi_gizle, migrations.RunPython.noop),
    ]
