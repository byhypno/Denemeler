from django.db import migrations


def cari_kasayi_kaldir(apps, schema_editor):
    """Cari Kasa kaldırılıyor. Veri kaybolmasın diye:
    - Hareketi ve gün sonu kapanışı olmayan Cari Kasa hesabı silinir.
    - Hareketi ya da gün sonu kaydı varsa hesap PASİF kalır (kayıtlar yönetim panelinde durur) ve her hareketin açıklamasına, düşecek
      alanların (tedarikçi) bilgisi '[Tedarikçi: ...]' olarak yazılır."""
    Hesap = apps.get_model("defter", "Hesap")
    Hareket = apps.get_model("defter", "KasaHareketi")
    GunSonu = apps.get_model("defter", "GunSonu")
    for h in Hesap.objects.filter(cari_bagli=True):
        hareketler = Hareket.objects.filter(hesap=h)
        if not hareketler.exists() and not GunSonu.objects.filter(hesap=h).exists():
            h.delete()                      # hareketi de gün sonu kaydı da yok: güvenle silinir (GunSonu.hesap PROTECT)
            continue
        for k in hareketler.select_related("cari", "ilgili_odeme"):
            ek = []
            if k.cari_id:
                ek.append(f"Tedarikçi: {k.cari.unvan}")
            if k.ilgili_odeme_id:
                ek.append(f"İlgili cari ödemesi: {k.ilgili_odeme.tarih:%d.%m.%Y}")
            if ek:
                Hareket.objects.filter(pk=k.pk).update(aciklama=(f"[{'; '.join(ek)}] " + (k.aciklama or ""))[:250])
        Hesap.objects.filter(pk=h.pk).update(aktif=False)


class Migration(migrations.Migration):
    dependencies = [("defter", "0014_cari_kasa_on_yuzde_gizli")]
    operations = [
        migrations.RunPython(cari_kasayi_kaldir, migrations.RunPython.noop),
        migrations.RemoveField(model_name="kasahareketi", name="ilgili_odeme"),
        migrations.RemoveField(model_name="kasahareketi", name="cari"),
        migrations.RemoveField(model_name="hesap", name="on_yuzde_gizli"),
        migrations.RemoveField(model_name="hesap", name="sadece_cikis"),
        migrations.RemoveField(model_name="hesap", name="cari_bagli"),
    ]
