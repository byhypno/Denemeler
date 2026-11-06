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
