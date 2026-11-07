"""Türkçe metin yardımcıları: aramada büyük/küçük harf ve aksan farkını yok sayar."""

_TR = str.maketrans({"İ": "i", "I": "i", "ı": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                     "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})


def katla(metin) -> str:
    """'ERÖZ Hırdavat' -> 'eroz hirdavat'. 'eroz', 'EROZ', 'Eröz' hepsi eşleşsin diye.

    SQLite'ın LIKE'ı yalnızca ASCII harflerde büyük/küçük ayırmaz ('İ' ile 'i' eşleşmez); bu yüzden Python'da karşılaştırılır.
    """
    return " ".join(str(metin or "").translate(_TR).lower().split())


def eslesir(arama, *alanlar) -> bool:
    """Arama sözcüklerinin HEPSİ alanlardan birinde geçiyorsa doğru (boş arama her şeyle eşleşir)."""
    samanlik = katla(" ".join(str(a or "") for a in alanlar))
    return all(s in samanlik for s in katla(arama).split())


def guvenli_int(deger):
    """'12' -> 12; bozuk girdi ('abc', '²', '', None, çok uzun) -> None. `str.isdigit()` '²' gibi karakterlerde doğru döner ama
    `int()` patlar; istek parametreleri bu yardımcıyla sayıya çevrilmelidir. Negatif sayı kabul edilmez."""
    try:
        n = int(str(deger).strip())
    except (TypeError, ValueError):
        return None
    return n if 0 <= n < 2**63 else None


def turkce_sirala(nesneler, anahtar=lambda x: x):
    """Türkçe alfabe sırası (Ç, Ö, Ş, İ, Ü Z'den sonraya düşmesin): `katla` ile karşılaştırır."""
    return sorted(nesneler, key=lambda x: katla(anahtar(x)))
