"""Logo varyantlarını üretir (Pillow gerekir: pip install pillow; yalnızca logo değiştirilirken lazım, program çalışırken gerekmez).

Kullanım:  python araclar/logo_uret.py <kaynak_logo.png> [--sembol-alt-sinir 610]

Kaynak: şeffaf arka planlı (RGBA) kare ya da yatay logo; üstte simge (ev + dalga), altta yazı.
Üretilenler (defter/static/defter/img/): logo.png (açık tema), logo-koyu.png (koyu tema: siyah yazı açık renge çevrilir),
logo-sembol.png (yalnızca simge; menü, üst şerit, yönetim paneli), favicon.png (simge).
`--sembol-alt-sinir`: simgenin bittiği, yazının başladığı satır (piksel, kaynak boyutunda).
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

HEDEF = Path(__file__).resolve().parent.parent / "defter" / "static" / "defter" / "img"
ACIK_YAZI = (230, 234, 244)          # koyu temanın --metin rengi


def koyu_surum(im: Image.Image) -> Image.Image:
    """Renksiz (siyah/gri) pikselleri açık renge çevirir; kırmızı/turuncu aynen kalır. Alfa korunur."""
    im = im.convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a and max(r, g, b) - min(r, g, b) < 40:                  # renksiz
                k = 1 - max(r, g, b) / 255                               # siyaha yakınlık (kenar yumuşatması korunur)
                px[x, y] = tuple(int(c * (1 - k) + c2 * k) for c, c2 in zip((r, g, b), ACIK_YAZI)) + (a,)
    return im


def kirp(im: Image.Image, kutu=None, bosluk=0) -> Image.Image:
    kutu = kutu or im.getchannel("A").getbbox()
    k = im.crop(kutu)
    if bosluk:
        tuval = Image.new("RGBA", (k.width + 2 * bosluk, k.height + 2 * bosluk), (0, 0, 0, 0))
        tuval.paste(k, (bosluk, bosluk))
        return tuval
    return k


def kare(im: Image.Image, boyut: int) -> Image.Image:
    """Ortalanmış, oranı korunmuş kare tuval (favicon)."""
    im = im.copy()
    im.thumbnail((boyut, boyut), Image.LANCZOS)
    tuval = Image.new("RGBA", (boyut, boyut), (0, 0, 0, 0))
    tuval.paste(im, ((boyut - im.width) // 2, (boyut - im.height) // 2))
    return tuval


def uret(kaynak, sembol_alt=610, hedef=HEDEF):
    hedef = Path(hedef)
    hedef.mkdir(parents=True, exist_ok=True)
    im = Image.open(kaynak).convert("RGBA")
    if im.getchannel("A").getextrema()[0] == 255:
        raise SystemExit("Kaynak logoda şeffaf arka plan yok (alfa kanalı gerekir).")
    tam = kirp(im, bosluk=8)
    sembol_kutu = im.crop((0, 0, im.width, sembol_alt)).getchannel("A").getbbox()
    sembol = kirp(im.crop((0, 0, im.width, sembol_alt)), sembol_kutu, bosluk=4)

    def kaydet(resim, ad, genislik):
        r = resim.copy()
        r.thumbnail((genislik, genislik * 4), Image.LANCZOS)
        r.save(hedef / ad, optimize=True)
        return r.size

    boyutlar = {"logo.png": kaydet(tam, "logo.png", 640), "logo-koyu.png": kaydet(koyu_surum(tam), "logo-koyu.png", 640),
                "logo-sembol.png": kaydet(sembol, "logo-sembol.png", 360)}
    kare(sembol, 128).save(hedef / "favicon.png", optimize=True)          # yalnızca simge: açık ve koyu sekmede de okunur
    boyutlar["favicon.png"] = (128, 128)
    return boyutlar


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kaynak")
    ap.add_argument("--sembol-alt-sinir", type=int, default=610)
    a = ap.parse_args()
    for ad, boyut in uret(a.kaynak, a.sembol_alt_sinir).items():
        print(f"{ad}: {boyut[0]}x{boyut[1]}")
    sys.exit(0)
