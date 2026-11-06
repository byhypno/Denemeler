from collections import Counter, defaultdict

from django.db import migrations

KATEGORILER = ["Kaynak malzemeleri", "El aletleri", "Elektrikli / akülü aletler", "Boya ve yapıştırıcı",
               "Vida ve bağlantı elemanları", "Elektrik malzemeleri", "Sarf malzeme", "Diğer"]

_TR = str.maketrans({"İ": "i", "I": "i", "ı": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                     "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})


def _katla(metin):
    """metin.katla ile aynı (geçişler uygulama koduna bağlı kalmasın diye kopya)."""
    return " ".join(str(metin or "").translate(_TR).lower().split())


def doldur(apps, schema_editor):
    """Hazır kategoriler gelir. Mevcut fiş kalemleri açıklamalarına göre (büyük/küçük harf ve aksan farkı yok sayılarak)
    malzemelere gruplanır ve bağlanır. Kategoriler tahmin EDİLMEZ: malzemeler 'kategorisiz' başlar, Malzemeler sayfasından atanır."""
    Kat = apps.get_model("defter", "MalzemeKategori")
    Malzeme = apps.get_model("defter", "Malzeme")
    Kalem = apps.get_model("defter", "BelgeKalem")
    for i, ad in enumerate(KATEGORILER, start=1):
        Kat.objects.get_or_create(ad=ad, defaults={"sira": i * 10 if ad != "Diğer" else 900})
    gruplar = defaultdict(list)
    for k in Kalem.objects.filter(malzeme__isnull=True).only("id", "aciklama", "birim"):
        anahtar = _katla(k.aciklama)
        if anahtar:
            gruplar[anahtar].append(k)
    for anahtar, kalemler in gruplar.items():
        yazim = Counter(" ".join(k.aciklama.split()) for k in kalemler).most_common(1)[0][0]
        birimler = Counter(k.birim for k in kalemler if k.birim).most_common(1)
        m = Malzeme.objects.filter(ad=yazim[:200]).first() or Malzeme.objects.create(
            ad=yazim[:200], birim=birimler[0][0] if birimler else "")
        Kalem.objects.filter(pk__in=[k.pk for k in kalemler]).update(malzeme=m)


class Migration(migrations.Migration):
    dependencies = [("defter", "0017_malzeme")]
    operations = [migrations.RunPython(doldur, migrations.RunPython.noop)]
