"""Örnek satış verisi üretir veya kullanıcının yüklediği CSV'yi okur."""
import numpy as np
import pandas as pd

REQUIRED = ["tarih", "urun", "kategori", "bolge", "adet", "fiyat"]


def sample_data(seed: int = 42, days: int = 365) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    urunler = {
        "Laptop": ("Elektronik", 25000), "Telefon": ("Elektronik", 18000),
        "Kulaklık": ("Elektronik", 1500), "Kitap": ("Kırtasiye", 150),
        "Defter": ("Kırtasiye", 60), "Sandalye": ("Mobilya", 2200),
        "Masa": ("Mobilya", 4500),
    }
    bolgeler = ["Marmara", "Ege", "İç Anadolu", "Akdeniz", "Karadeniz"]
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days)
    rows = []
    for d in dates:
        trend = 1 + 0.4 * (d - dates[0]).days / days
        for _ in range(rng.poisson(8 * trend)):
            u = rng.choice(list(urunler))
            kat, fiyat = urunler[u]
            rows.append((d, u, kat, rng.choice(bolgeler),
                         int(rng.integers(1, 4)),
                         round(fiyat * rng.uniform(0.9, 1.1), 2)))
    return pd.DataFrame(rows, columns=REQUIRED)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Eksik sütunlar: {', '.join(missing)}")
    df = df[REQUIRED].copy()
    df["tarih"] = pd.to_datetime(df["tarih"], errors="coerce")
    df = df.dropna(subset=["tarih"])
    df["ciro"] = df["adet"] * df["fiyat"]
    return df
