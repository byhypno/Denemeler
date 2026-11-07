"""Malzeme kataloğu: alış fiyatı geçmişi, son fiyat, zam tespiti, malzeme eşleme ve birleştirme.

Fiyat HAFIZASI ayrı bir tabloda tutulmaz; fiş kalemlerinden (iptal edilmemiş belgeler) hesaplanır, bu yüzden kalem
iptal/düzeltmeleriyle her zaman tutarlıdır. "Son fiyat" = belge tarihine göre (eşitse belge sırasına göre) EN SON alış.
Birim fiyat = kalemde girilen birim fiyat; yoksa tutar ÷ miktar. Kalem tutarları fişte yazan (çoğunlukla KDV hariç) tutarlardır.
"""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from . import metin
from .models import BelgeKalem, Malzeme

KURUS = Decimal(1)


def birim_fiyat(kalem) -> Decimal:
    """Kalemin birim fiyatı, KURUŞ cinsinden (Decimal, 4 hane)."""
    if kalem.birim_fiyat:                               # 0 / boş: tutar ÷ miktar kullanılır
        f = Decimal(kalem.birim_fiyat) * 100
    else:
        f = Decimal(kalem.tutar_kurus) / Decimal(kalem.miktar)
    return f.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _degisim(yeni: Decimal, eski: Decimal):
    """{"yon","yuzde"} (yuzde bir ondalık) ya da None. Kuruşun altındaki fark 'yatay' sayılır."""
    if eski is None or eski <= 0:                       # fiyatı 0 olan eski kayıt: oran tanımsız (sıfıra bölme olmasın)
        return None
    fark = yeni - eski
    if abs(fark) < Decimal("0.5"):
        return {"yon": "yatay", "yuzde": Decimal(0)}
    yuzde = (abs(fark) * 100 / eski).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return {"yon": "yukari" if fark > 0 else "asagi", "yuzde": yuzde}


def _kalemler(malzeme=None):
    qs = (BelgeKalem.objects.filter(belge__iptal=False, malzeme__isnull=False)
          .select_related("belge", "belge__cari", "malzeme"))
    if malzeme is not None:
        qs = qs.filter(malzeme=malzeme)
    return sorted(qs, key=lambda k: (k.belge.tarih, k.belge_id, k.sira, k.pk))


def _satir(k, onceki_fiyat):
    f = birim_fiyat(k)
    return {"kalem": k, "tarih": k.belge.tarih, "cari": k.belge.cari, "belge": k.belge, "miktar": k.miktar,
            "birim": k.birim or k.malzeme.birim, "fiyat": f, "tutar_kurus": k.tutar_kurus, "degisim": _degisim(f, onceki_fiyat)}


def fiyat_gecmisi(malzeme):
    """Malzemenin alışları, eskiden yeniye. Her satırda bir ÖNCEKİ alışa göre değişim (tedarikçiden bağımsız)."""
    satirlar, onceki = [], None
    for k in _kalemler(malzeme):
        s = _satir(k, onceki)
        satirlar.append(s)
        onceki = s["fiyat"]
    return satirlar


def ozet_tablo():
    """{malzeme_id: {"son","onceki","degisim","adet","toplam_kurus","en_dusuk","en_yuksek"}} — tüm malzemeler tek geçişte."""
    gruplar = defaultdict(list)
    for k in _kalemler():
        gruplar[k.malzeme_id].append(k)
    sonuc = {}
    for mid, ks in gruplar.items():
        fiyatlar = [birim_fiyat(k) for k in ks]
        son = _satir(ks[-1], fiyatlar[-2] if len(ks) > 1 else None)
        onceki = _satir(ks[-2], None) if len(ks) > 1 else None
        sonuc[mid] = {"son": son, "onceki": onceki, "degisim": son["degisim"], "adet": len(ks),
                      "toplam_kurus": sum(k.tutar_kurus for k in ks), "en_dusuk": min(fiyatlar), "en_yuksek": max(fiyatlar)}
    return sonuc


def katla_haritasi():
    """{katla(ad): Malzeme} — çok kalemli bir kayıtta tabloyu her kalem için baştan taramamak için BİR kez kurulur."""
    return {metin.katla(m.ad): m for m in Malzeme.objects.all()}


def malzeme_bul_veya_olustur(ad, birim="", harita=None):
    """Açıklamaya (büyük/küçük harf ve aksan farkı yok sayılarak) uyan malzemeyi bulur; yoksa kategorisiz yeni malzeme açar.
    `harita` verilirse (katla_haritasi) tablo taranmaz; yeni malzeme haritaya da eklenir."""
    ad = " ".join((ad or "").split())[:200]
    anahtar = metin.katla(ad)
    if harita is None:
        harita = katla_haritasi()
    m = harita.get(anahtar)
    if m is not None:
        while m.birlestirildi_id:                      # birleştirilmiş eski ad yazılırsa kayıt birleştirildiği malzemeye gider
            m = m.birlestirildi
        return m, False
    m = Malzeme.objects.create(ad=ad, birim=(birim or "")[:20])
    harita[anahtar] = m
    return m, True


def hafiza_verisi():
    """Fiş formu için: aktif malzemeler ve son alış bilgisi (JS ipucu ve zam uyarısı bunu kullanır)."""
    ozet = ozet_tablo()
    veri = []
    for m in metin.turkce_sirala(Malzeme.objects.filter(aktif=True), lambda m: m.ad):
        o = ozet.get(m.pk)
        d = {"ad": m.ad, "birim": m.birim}
        if o:
            s = o["son"]
            d.update(fiyat=f"{s['fiyat'] / 100:.4f}", tarih=f"{s['tarih']:%d.%m.%Y}", cari=s["cari"].unvan)
        veri.append(d)
    return veri


def zam_uyarilari(kalemler):
    """Yeni kaydedilen kalemleri, kendilerinden ÖNCEKİ alışla karşılaştırır. Dönüş: yalnızca ZAM olanlar
    [{"malzeme","onceki","yeni","yuzde","onceki_cari","onceki_tarih"}]"""
    uyarilar = []
    for k in kalemler:
        gecmis = fiyat_gecmisi(k.malzeme)
        idx = next((i for i, s in enumerate(gecmis) if s["kalem"].pk == k.pk), None)
        if idx is None or idx == 0:
            continue
        s, o = gecmis[idx], gecmis[idx - 1]
        d = s["degisim"]
        if d and d["yon"] == "yukari":
            uyarilar.append({"malzeme": k.malzeme, "onceki": o["fiyat"], "yeni": s["fiyat"], "yuzde": d["yuzde"],
                             "onceki_cari": o["cari"], "onceki_tarih": o["tarih"]})
    return uyarilar


@transaction.atomic
def birlestir(kaynak, hedef):
    """`kaynak` malzemenin tüm kalemlerini `hedef`e taşır; kaynak pasif yapılır (silinmez, günlükte kalır)."""
    if kaynak.pk == hedef.pk:
        raise ValueError("Bir malzeme kendisiyle birleştirilemez.")
    for k in BelgeKalem.objects.filter(malzeme=kaynak):
        k.malzeme = hedef
        k.save()
    kaynak.aktif = False
    kaynak.birlestirildi = hedef
    kaynak.save()
    for m in Malzeme.objects.filter(birlestirildi=kaynak):      # zincir kısalsın: eskiden kaynağa birleşenler de hedefe bağlanır
        m.birlestirildi = hedef
        m.save()
    if not hedef.birim and kaynak.birim:
        hedef.birim = kaynak.birim
        hedef.save()
    return hedef


def yuzde_metni(yuzde) -> str:
    return f"{yuzde}".replace(".", ",")
