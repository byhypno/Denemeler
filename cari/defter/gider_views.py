"""Aylık net genel giderler sayfası: ay girişi, yıllık tablo, özet kartları, grafik, Excel."""
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import gider_servisi as gs
from . import metin, trend
from .models import GiderKategori
from .yetki import var_mi, yetki_gerekli


def _yil_ay(veri, bugun):
    try:
        yil = int(veri.get("yil", ""))
    except ValueError:
        yil = bugun.year
    if not (2000 <= yil <= 2100):
        yil = bugun.year
    try:
        ay = int(veri.get("ay", ""))
    except ValueError:
        ay = bugun.month if yil == bugun.year else 12
    if not (1 <= ay <= 12):
        ay = bugun.month if yil == bugun.year else 12
    return yil, ay


def _geri(yil, ay):
    return redirect(f"{reverse('giderler')}?yil={yil}&ay={ay}")


@yetki_gerekli("goruntule", "veri_gir")
def giderler(request):
    bugun = date.today()
    yil, ay = _yil_ay(request.GET, bugun)
    kategoriler = gs.kategoriler_yil(yil)

    girdi, hatalar = {}, []
    if request.method == "POST":
        eylem = request.POST.get("eylem", "kaydet")
        if eylem == "kopyala":
            n = gs.onceki_aydan_kopyala(yil, ay, kategoriler)
            if n:
                messages.success(request, f"Önceki aydan {n} kalem kopyalandı (dolu satırlara dokunulmadı).")
            else:
                messages.info(request, "Kopyalanacak kalem yok: önceki ayda gider yok ya da bu ayın satırları zaten dolu.")
            return _geri(yil, ay)
        try:
            n = gs.kaydet(yil, ay, request.POST, kategoriler)
        except ValidationError as e:
            hatalar, girdi = e.messages, request.POST
        else:
            messages.success(request, f"{trend.AY_ADLARI[ay - 1]} {yil} giderleri kaydedildi." if n else "Değişiklik yok.")
            return _geri(yil, ay)

    tablo = gs.yillik_tablo(yil)
    if request.GET.get("indir") == "xlsx":
        yanit = HttpResponse(gs.yillik_xlsx(yil, tablo),
                             content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        yanit["Content-Disposition"] = f'attachment; filename="genel_gider_{yil}.xlsx"'
        return yanit

    ozet = gs.ozet(yil, ay, tablo)
    satirlar = []
    for k in kategoriler:
        kurus = tablo["hucre"].get((k.pk, ay), 0)
        satirlar.append({"kategori": k, "kurus": kurus, "not": tablo["notlar"].get((k.pk, ay), ""),
                         "girdi_tutar": girdi.get(f"tutar_{k.pk}") if girdi else None,
                         "girdi_not": girdi.get(f"not_{k.pk}") if girdi else None})
    grafik = {"aylar": trend.AY_ADLARI_KISA,
              "seriler": [{"ad": k.ad, "veri": [tablo["hucre"].get((k.pk, a), 0) for a in range(1, 13)]}
                          for k in kategoriler if tablo["kat_toplam"].get(k.pk)],
              "toplam": tablo["ay_toplam"]}
    return render(request, "defter/giderler.html", {
        "yil": yil, "ay": ay, "ay_adi": trend.AY_ADLARI[ay - 1], "yillar": gs.yillar(bugun), "kategoriler": kategoriler,
        "tablo": tablo, "ozet": ozet, "satirlar": satirlar, "hatalar": hatalar, "aylar": list(enumerate(trend.AY_ADLARI_KISA, start=1)),
        "grafik": grafik, "toplam_seri": tablo["ay_toplam"], "yazabilir": var_mi(request.user, "veri_gir"),
        "sayfa": "giderler", "bugun": bugun,
    })


@yetki_gerekli("goruntule", "veri_gir")
@require_POST
def gider_kategori_ekle(request):
    ad = " ".join(request.POST.get("ad", "").split())
    yil, ay = _yil_ay(request.POST, date.today())
    if not ad:
        messages.error(request, "Kategori adı yazın.")
    elif len(ad) > 80:
        messages.error(request, "Kategori adı en fazla 80 karakter olabilir.")
    elif any(metin.katla(k.ad) == metin.katla(ad) for k in GiderKategori.objects.all()):
        messages.error(request, f"'{ad}' kategorisi zaten var (büyük/küçük harf ve aksan farkı yok sayılır).")
    else:
        sira = (GiderKategori.objects.order_by("-sira").values_list("sira", flat=True).first() or 0) + 10
        # "Diğer" hep en sonda kalsın
        GiderKategori.objects.create(ad=ad, sira=min(sira, 900) if ad != "Diğer" else 999)
        messages.success(request, f"'{ad}' kategorisi eklendi.")
    return _geri(yil, ay)
