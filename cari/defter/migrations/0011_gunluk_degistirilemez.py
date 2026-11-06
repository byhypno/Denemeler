from django.db import migrations

# Güvenlik ağı: uygulama hatası, yönetim paneli veya yanlış bir SQL günlüğü değiştiremesin/silemesin.
# (Veritabanı dosyasına doğrudan erişen biri tetikleyicileri kaldırabilir; bu kasıtlı kurcalamaya karşı değil,
#  kazaya ve uygulama hatasına karşı bir koruma katmanıdır.)
# NOT: SQLite'ta bu tabloya yapılacak sonraki şema değişiklikleri tabloyu yeniden kurar ve tetikleyicileri düşürür;
# öyle bir geçiş yazarsanız tetikleyicileri yeniden oluşturun.
ILERI = [
    """CREATE TRIGGER islemgunlugu_guncelleme_yasak BEFORE UPDATE ON defter_islemgunlugu
       BEGIN SELECT RAISE(ABORT, 'Islem gunlugu degistirilemez'); END;""",
    """CREATE TRIGGER islemgunlugu_silme_yasak BEFORE DELETE ON defter_islemgunlugu
       BEGIN SELECT RAISE(ABORT, 'Islem gunlugu silinemez'); END;""",
]
GERI = [
    "DROP TRIGGER IF EXISTS islemgunlugu_guncelleme_yasak;",
    "DROP TRIGGER IF EXISTS islemgunlugu_silme_yasak;",
]


class Migration(migrations.Migration):
    dependencies = [("defter", "0010_islem_gunlugu")]
    operations = [migrations.RunSQL(ILERI, GERI)]
