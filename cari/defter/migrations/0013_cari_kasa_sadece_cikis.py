from django.db import migrations, models


def cari_kasayi_ayarla(apps, schema_editor):
    """Cari Kasa geri açılır ve yalnızca tedarikçiye ödenen ücreti tutar: giriş yok, bakiye hep eksi (eksiye düşebilir)."""
    Hesap = apps.get_model("defter", "Hesap")
    Hesap.objects.filter(ad="Cari Kasa", cari_bagli=True).update(aktif=True, sadece_cikis=True, eksiye_dusebilir=True)


class Migration(migrations.Migration):
    dependencies = [("defter", "0012_cari_kasa_pasif")]
    operations = [
        migrations.AddField(model_name="hesap", name="sadece_cikis", field=models.BooleanField(
            default=False, verbose_name="Yalnızca çıkış (ödeme) kasası",
            help_text="İşaretliyse bu kasaya giriş yazılamaz; yalnızca tedarikçiye yapılan ödemeler (çıkış) girilir. Para alınmadığı için bakiye hep eksi kalır.")),
        migrations.RunPython(cari_kasayi_ayarla, migrations.RunPython.noop),
    ]
