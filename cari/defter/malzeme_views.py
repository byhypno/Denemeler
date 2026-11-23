"""Malzemeler: katalog, kategoriler, alış fiyatı geçmişi, zam takibi, birleştirme."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import malzeme_servisi as ms
from . import metin
from .models import Malzeme, MalzemeKategori
from .yetki import var_mi, yetki_gerekli

SIRALAR = {"ad": "Ada göre", "zam": "Son zam oranına göre", "son": "Son alış tarihine göre", "tutar": "Toplam alış tutarına göre"}
SAYFA_BOYU = 100
ZAM_PENCERE_GUN = 90        # "son zamlar" kutusu ve sayaç: son 90 gün içindeki alışlarda görülen zamlar


def _geri(request):
    """İşlemden sonra aynı süzgeçli listeye dön (yalnızca site içi, '?' ile başlayan sorgu)."""
    sorgu = request.GET.urlencode()
    return redirect(reverse("malzemeler") + (f"?{sorgu}" if sorgu else ""))


@yetki_gerekli("goruntule", "veri_gir")
def malzemeler(request):
    bugun = date.today()
    if request.method == "POST":
        eylem = request.POST.get("eylem")
        if eylem == "kategori_ekle":
            ad = " ".join(request.POST.get("ad", "").split())
            if not ad or len(ad) > 80:
                messages.error(request, "Kategori adı yazın (en fazla 80 karakter).")
            elif any(metin.katla(k.ad) == metin.katla(ad) for k in MalzemeKategori.objects.all()):
                messages.error(request, f"'{ad}' kategorisi zaten var (büyük/küçük harf ve aksan farkı yok sayılır).")
            else:
                sira = min((MalzemeKategori.objects.exclude(ad="Diğer").order_by("-sira").values_list("sira", flat=True).first() or 0) + 10, 890)
                MalzemeKategori.objects.create(ad=ad, sira=sira)
                messages.success(request, "Kategori eklendi.")
        elif eylem == "toplu_ata":
            secim = request.POST.get("kategori_toplu", "")
            kat = MalzemeKategori.objects.filter(pk=metin.guvenli_int(secim)).first() if metin.guvenli_int(secim) is not None else None
            idler = [n for n in map(metin.guvenli_int, request.POST.getlist("sec")) if n is not None]
            if not idler:
                messages.error(request, "Önce listeden malzeme seçin.")
            elif secim and kat is None:
                messages.error(request, "Kategoriyi seçin.")
            else:
                n = 0
                for m in Malzeme.objects.filter(pk__in=idler):
                    if m.kategori_id != (kat.pk if kat else None):
                        m.kategori = kat
                        m.save()
                        n += 1
                messages.success(request, f"{n} malzeme '{kat.ad if kat else 'kategorisiz'}' yapıldı." if n else "Değişiklik yok.")
        elif eylem == "kategori_kaydet":
            n = 0
            kategoriler = {str(k.pk): k for k in MalzemeKategori.objects.all()}
            for m in Malzeme.objects.filter(pk__in=[n for n in map(metin.guvenli_int, request.POST.getlist("idler")) if n is not None]):
                secim = request.POST.get(f"kategori_{m.pk}", "")
                yeni = kategoriler.get(secim)           # "" ya da bilinmeyen: kategorisiz
                if (yeni.pk if yeni else None) != m.kategori_id:
                    m.kategori = yeni
                    m.save()
                    n += 1
            messages.success(request, f"{n} malzemenin kategorisi güncellendi." if n else "Değişiklik yok.")
        return _geri(request)

    q = request.GET.get("q", "").strip()
    kategori = request.GET.get("kategori", "")
    sadece_zam = request.GET.get("zam") == "1"
    pasifler = request.GET.get("pasif") == "1"
    sira = request.GET.get("sira", "ad")
    sira = sira if sira in SIRALAR else "ad"

    ozet = ms.ozet_tablo()
    kategoriler = list(MalzemeKategori.objects.filter(aktif=True))
    zam_siniri = bugun - timedelta(days=ZAM_PENCERE_GUN)
    tum, satirlar = 0, []
    for m in Malzeme.objects.select_related("kategori"):
        if not m.aktif and not pasifler:
            continue
        tum += 1 if m.aktif else 0
        o = ozet.get(m.pk)
        zam = bool(o and o["degisim"] and o["degisim"]["yon"] == "yukari")
        if sadece_zam and not zam:
            continue
        if kategori == "yok" and m.kategori_id:
            continue
        if metin.guvenli_int(kategori) is not None and m.kategori_id != metin.guvenli_int(kategori):
            continue
        if not metin.eslesir(q, m.ad, m.kategori.ad if m.kategori else ""):
            continue
        satirlar.append({"m": m, "o": o, "zam": zam, "yeni_zam": bool(zam and o["son"]["tarih"] >= zam_siniri)})
    if sira == "ad":
        satirlar.sort(key=lambda r: metin.katla(r["m"].ad))
    elif sira == "zam":
        satirlar.sort(key=lambda r: -(r["o"]["degisim"]["yuzde"] if r["zam"] else -1))
    elif sira == "son":
        satirlar.sort(key=lambda r: r["o"]["son"]["tarih"] if r["o"] else date.min, reverse=True)
    else:
        satirlar.sort(key=lambda r: -(r["o"]["toplam_kurus"] if r["o"] else 0))

    sayfa_nesnesi = Paginator(satirlar, SAYFA_BOYU).get_page(request.GET.get("sayfa"))
    sorgu = request.GET.copy()
    sorgu.pop("sayfa", None)
    tumu = Malzeme.objects.filter(aktif=True)
    son_zamlar = sorted((r for r in ({"m": m, "o": ozet[m.pk]} for m in tumu if m.pk in ozet)
                         if r["o"]["degisim"] and r["o"]["degisim"]["yon"] == "yukari" and r["o"]["son"]["tarih"] >= zam_siniri),
                        key=lambda r: -r["o"]["degisim"]["yuzde"])
    return render(request, "defter/malzemeler.html", {
        "satirlar": list(sayfa_nesnesi.object_list), "sayfa_nesnesi": sayfa_nesnesi, "sorgu": sorgu.urlencode(), "bulunan": len(satirlar), "q": q, "kategori": kategori, "sadece_zam": sadece_zam, "pasifler": pasifler, "sira": sira, "siralar": SIRALAR,
        "kategoriler": kategoriler, "toplam": tum, "kategorisiz": sum(1 for m in tumu if not m.kategori_id),
        "son_zamlar": son_zamlar[:5], "zam_sayisi": len(son_zamlar), "zam_gun": ZAM_PENCERE_GUN,
        "toplam_tutar": sum(o["toplam_kurus"] for o in ozet.values()), "sayfa": "malzemeler", "yazabilir": var_mi(request.user, "veri_gir"),
    })


@yetki_gerekli("goruntule", "veri_gir")
def malzeme_detay(request, pk):
    m = get_object_or_404(Malzeme.objects.select_related("kategori"), pk=pk)
    if request.method == "POST":
        eylem = request.POST.get("eylem")
        if eylem == "duzenle":
            ad = " ".join(request.POST.get("ad", "").split())
            hata = None
            if not ad or len(ad) > 200:
                hata = "Malzeme adı yazın (en fazla 200 karakter)."
            elif any(x.pk != m.pk and metin.katla(x.ad) == metin.katla(ad) for x in Malzeme.objects.all()):
                hata = f"'{ad}' adlı başka bir malzeme var; ikisini birleştirmek için Birleştir'i kullanın."
            if hata:
                messages.error(request, hata)
            else:
                secim = request.POST.get("kategori", "")
                m.ad = ad
                m.kategori = MalzemeKategori.objects.filter(pk=metin.guvenli_int(secim)).first() if metin.guvenli_int(secim) is not None else None
                m.birim = request.POST.get("birim", "").strip()[:20]
                m.aktif = request.POST.get("aktif") == "on"
                m.save()
                messages.success(request, "Malzeme güncellendi.")
        elif eylem == "birlestir":
            hedef = Malzeme.objects.filter(pk=metin.guvenli_int(request.POST.get("hedef")), aktif=True).first() if metin.guvenli_int(request.POST.get("hedef")) is not None else None
            if hedef is None or hedef.pk == m.pk:
                messages.error(request, "Birleştirilecek malzemeyi seçin.")
            else:
                ms.birlestir(m, hedef)
                messages.success(request, f"'{m.ad}' kalemleri '{hedef.ad}' malzemesine taşındı; '{m.ad}' pasif yapıldı.")
                return redirect("malzeme_detay", pk=hedef.pk)
        return redirect("malzeme_detay", pk=m.pk)

    gecmis = ms.fiyat_gecmisi(m)
    son = gecmis[-1] if gecmis else None
    fiyatlar = [g["fiyat"] for g in gecmis]
    # tedarikçi karşılaştırması: her tedarikçinin SON alış fiyatı
    son_tedarikci = {}
    for g in gecmis:
        son_tedarikci[g["cari"].pk] = g
    tedarikciler = sorted(son_tedarikci.values(), key=lambda g: g["fiyat"])
    for g in tedarikciler:                         # en ucuz tedarikçiye göre fark (%)
        g["ucuza_gore"] = ((g["fiyat"] / tedarikciler[0]["fiyat"] - 1) * 100).quantize(Decimal("0.1"))
    etiketler = [f"{g['tarih']:%d.%m.%y}" for g in gecmis]
    seriler = {}
    for i, g in enumerate(gecmis):
        s = seriler.setdefault(g["cari"].unvan, [None] * len(gecmis))
        s[i] = float(g["fiyat"]) / 100
    return render(request, "defter/malzeme_detay.html", {
        "m": m, "gecmis": list(reversed(gecmis)), "son": son, "onceki": gecmis[-2] if len(gecmis) > 1 else None,
        "en_dusuk": min(fiyatlar) if fiyatlar else None, "en_yuksek": max(fiyatlar) if fiyatlar else None,
        "ortalama": (sum(fiyatlar) / len(fiyatlar)) if fiyatlar else None,
        "tedarikciler": tedarikciler, "kategoriler": MalzemeKategori.objects.filter(aktif=True),
        "digerleri": Malzeme.objects.filter(aktif=True).exclude(pk=m.pk), "yazabilir": var_mi(request.user, "veri_gir"),
        "grafik": {"etiketler": etiketler, "seriler": [{"ad": a, "veri": v} for a, v in seriler.items()]},
        "sayfa": "malzemeler",
    })
