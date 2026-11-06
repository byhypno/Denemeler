"""Gösterge kartlarındaki mini grafik (sparkline) ve 'önceki aya göre' değişim hesapları.

Saf fonksiyonlardır (veritabanına dokunmaz); test_trend.py ile sınanır.
"""
from datetime import date


def son_tam_ay_indeksi(yil: int, bugun: date) -> int:
    """Seçilen yılda tamamlanmış son ayın 0 tabanlı sırası (yoksa -1). Süren ay 'tam' sayılmaz."""
    if yil < bugun.year:
        return 11
    if yil > bugun.year:
        return -1
    return bugun.month - 2


def degisim(seri: list, yil: int, bugun: date):
    """Son tam ay ile ondan önceki ayı karşılaştırır.

    Dönüş: None (karşılaştırılamaz) veya {"yon": "yukari"|"asagi"|"yatay", "yuzde": int|None}.
    Önceki ay 0 ise yüzde hesaplanamaz (yuzde=None): yalnızca yön verilir.
    """
    i = son_tam_ay_indeksi(yil, bugun)
    if i < 1 or i >= len(seri):
        return None
    son, onceki = seri[i], seri[i - 1]
    if son is None or onceki is None:
        return None
    fark = son - onceki
    yon = "yatay" if fark == 0 else ("yukari" if fark > 0 else "asagi")
    yuzde = None if onceki == 0 else round(abs(fark) * 100 / abs(onceki))
    if yuzde == 0 and fark != 0:
        yuzde = 1                      # '%0' ama yön var: yanıltıcı olmasın
    return {"yon": yon, "yuzde": yuzde}


def sparkline_yollari(seri: list, genislik: int = 92, yukseklik: int = 32, bosluk: int = 3):
    """Seri -> (cizgi_yolu, alan_yolu) SVG path metinleri. 2'den az nokta varsa None.

    None değerler (gelecek aylar) atlanır. Seri sabitse çizgi ortada düz çizilir.
    """
    noktalar = [v for v in seri if v is not None]
    if len(noktalar) < 2:
        return None
    lo, hi = min(noktalar), max(noktalar)
    n = len(noktalar)
    ic_g, ic_y = genislik - 2 * bosluk, yukseklik - 2 * bosluk
    xy = []
    for k, v in enumerate(noktalar):
        x = bosluk + ic_g * k / (n - 1)
        y = yukseklik / 2 if hi == lo else bosluk + ic_y * (1 - (v - lo) / (hi - lo))
        xy.append((round(x, 1), round(y, 1)))
    cizgi = "M" + " L".join(f"{x} {y}" for x, y in xy)
    alan = f"{cizgi} L{xy[-1][0]} {yukseklik} L{xy[0][0]} {yukseklik} Z"
    return cizgi, alan


AY_ADLARI = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def ay_gruplari(satirlar: list, onceki: int = 0) -> list:
    """[(belge, bakiye)] (tarih sıralı) -> ay ay gruplar.

    Her grup: {"yil", "ay", "ad", "satirlar", "artis", "azalis", "acilis", "kapanis"} (kuruş).
    acilis = o aya girerken bakiye, kapanis = ay sonu bakiyesi (grubun son satırı).
    """
    gruplar = []
    onceki_bakiye = onceki
    for belge, bakiye in satirlar:
        t = belge.tarih
        if not gruplar or (gruplar[-1]["yil"], gruplar[-1]["ay"]) != (t.year, t.month):
            gruplar.append({"yil": t.year, "ay": t.month, "ad": f"{AY_ADLARI[t.month - 1]} {t.year}",
                            "satirlar": [], "artis": 0, "azalis": 0, "acilis": onceki_bakiye, "kapanis": bakiye})
        g = gruplar[-1]
        g["satirlar"].append((belge, bakiye))
        if belge.etki > 0:
            g["artis"] += belge.tutar_kurus
        else:
            g["azalis"] += belge.tutar_kurus
        g["kapanis"] = bakiye
        onceki_bakiye = bakiye
    return gruplar
