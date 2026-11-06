from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render

from . import ek_servisi as es
from . import odeme_listesi as ol
from . import services, trend
from .models import Belge, Cari, EkstreMutabakat
from .yetki import oturum_gerekli, var_mi, yetki_gerekli

AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
yonetici_gerekli = yetki_gerekli("yonetim")   # yalnızca yönetici (superuser)


@oturum_gerekli
def dashboard(request):
    if not var_mi(request.user, "goruntule"):
        if var_mi(request.user, "kasa_goruntule"):          # ör. Kasiyer: doğrudan kasaya
            return redirect("kasa")
        raise PermissionDenied("Bu sayfa için yetkiniz yok.")
    bugun = date.today()
    yillar = sorted({d.year for d in Belge.objects.filter(iptal=False).dates("tarih", "year")}) \
        or [bugun.year]
    try:
        yil = int(request.GET.get("yil", ""))
    except ValueError:
        yil = yillar[-1]
    if yil not in yillar:
        yil = yillar[-1]
    cari = None
    cari_id = request.GET.get("cari", "")
    if cari_id.isdigit():
        cari = Cari.objects.filter(pk=int(cari_id)).first()

    aylik = services.aylik_ozet(yil, cari, bugun)
    yas = services.yaslandirma(bugun, cari)
    bakiyeler = services.cari_bakiyeleri()
    borclular = [(c, b) for c, b in bakiyeler if b > 0][:10]
    kalemler = services.en_cok_alinan_kalemler(yil, cari)
    kontrol = services.kontrol_listesi(bugun)

    if cari:
        guncel_borc = services.bakiye_kurus(cari)
        mutabakatlar = [oz for oz in kontrol["mutabakat"] if oz["mutabakat"].cari_id == cari.pk]
    else:
        guncel_borc = sum(b for _, b in bakiyeler if b > 0)
        mutabakatlar = kontrol["mutabakat"]
    acik_fark = sum(abs(oz["fark_kurus"]) for oz in mutabakatlar)

    grafik = {
        "aylar": AYLAR,
        "alis": aylik["alis"], "iade": aylik["iade"], "odeme": aylik["odeme"],
        "ay_sonu": aylik["ay_sonu"],
        "yas_etiket": yas["etiketler"], "yas_deger": yas["kovalar"],
        "borclu_etiket": [c.unvan for c, _ in borclular], "borclu_deger": [b for _, b in borclular],
        "kalem_etiket": [a for a, _ in kalemler], "kalem_deger": [t for _, t in kalemler],
    }
    degisimler = {ad: trend.degisim(aylik[ad], yil, bugun) for ad in ("alis", "odeme", "iade", "ay_sonu")}
    return render(request, "defter/dashboard.html", {
        "yil": yil, "aylik": aylik, "degisimler": degisimler, "yillar": yillar, "cari": cari, "cariler": Cari.objects.all(),
        "guncel_borc": guncel_borc, "yil_alis": sum(aylik["alis"]),
        "yil_odeme": sum(aylik["odeme"]), "yil_iade": sum(aylik["iade"]),
        "acik_fark": acik_fark, "kontrol": kontrol, "yas": yas, "borclular": borclular,
        "grafik": grafik, "veri_var": Belge.objects.filter(iptal=False).exists(),
        "bugun": bugun, "sayfa": "dashboard",
    })


@yetki_gerekli("goruntule")
def mutabakat_liste(request):
    ozetler = [services.mutabakat_ozeti(m) for m in
               EkstreMutabakat.objects.select_related("cari")]
    return render(request, "defter/mutabakat_liste.html", {"ozetler": ozetler, "sayfa": "mutabakat"})


@yetki_gerekli("goruntule")
def mutabakat_detay(request, pk):
    m = get_object_or_404(EkstreMutabakat.objects.select_related("cari"), pk=pk)
    return render(request, "defter/mutabakat_detay.html",
                  {"oz": services.mutabakat_ozeti(m), "sayfa": "mutabakat",
                   "ek_sayisi": m.ekler.filter(kaldirildi=False).count()})


class _Donem(forms.Form):
    bas = forms.DateField(required=False)
    bit = forms.DateField(required=False)


@yetki_gerekli("goruntule")
def cari_ekstre(request, pk):
    cari = get_object_or_404(Cari, pk=pk)
    f = _Donem(request.GET)
    bas = bit = None
    hata = ""
    if f.is_valid():
        bas, bit = f.cleaned_data["bas"], f.cleaned_data["bit"]
    else:
        hata = "Tarihi gg.aa.yyyy biçiminde girin."
    onceki, satirlar = services.ekstre(cari, bas, bit)
    kapanis = satirlar[-1][1] if satirlar else onceki
    gruplar = trend.ay_gruplari(satirlar, onceki)
    def topla(*turler):
        return sum(b.tutar_kurus for b, _ in satirlar if b.tur in turler)
    # hızlı ay seçimi: carinin hareket gördüğü son 12 ay
    aylar = []
    for d in list(Belge.objects.filter(cari=cari, iptal=False).dates("tarih", "month"))[-12:]:
        son = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        aylar.append({"ad": f"{trend.AY_ADLARI[d.month - 1][:3]} {d.year}", "bas": f"{d:%d.%m.%Y}", "bit": f"{son:%d.%m.%Y}",
                      "aktif": bas == d and bit == son})
    eksi_ay = sum(1 for g in gruplar if g["kapanis"] < 0)
    return render(request, "defter/ekstre.html", {
        "ek_sayi": es.ek_sayilari([b.pk for b, _ in satirlar], "belge"),
        "cari_ek_sayisi": cari.ekler.filter(kaldirildi=False).count(),
        "cari": cari, "onceki": onceki, "satirlar": satirlar, "kapanis": kapanis, "gruplar": gruplar,
        "bas": bas, "bit": bit, "hata": hata, "sayfa": "ekstre", "aylar": aylar, "eksi_ay": eksi_ay,
        "guncel_borc": services.bakiye_kurus(cari),
        "bakiye_seri": [g["kapanis"] for g in gruplar],
        "alis_toplam": topla(Belge.Tur.ALIS_FISI, Belge.Tur.ALIS_FATURASI),
        "odeme_toplam": topla(Belge.Tur.ODEME), "iade_toplam": topla(Belge.Tur.IADE),
        "toplam_artis": sum(b.tutar_kurus for b, _ in satirlar if b.etki > 0),
        "toplam_azalis": sum(b.tutar_kurus for b, _ in satirlar if b.etki < 0),
    })


class _ListeFiltre(forms.Form):
    liste = forms.ChoiceField(choices=[("odenecek", "Ödenecekler"), ("yapilan", "Yapılan ödemeler")],
                              required=False)
    bas = forms.DateField(required=False)
    bit = forms.DateField(required=False)
    cari = forms.ModelChoiceField(Cari.objects.all(), required=False)
    sekil = forms.ChoiceField(choices=[("", "Tümü"), *Belge.OdemeSekli.choices], required=False)
    indir = forms.ChoiceField(choices=[("", ""), ("xlsx", "xlsx")], required=False)


@yetki_gerekli("goruntule")
def odeme_listesi(request):
    bugun = date.today()
    f = _ListeFiltre(request.GET)
    hata = ""
    if f.is_valid():
        v = f.cleaned_data
    else:
        v = {}
        hata = "Filtre değerleri geçersiz; varsayılanlar gösteriliyor."
    liste = v.get("liste") or "odenecek"
    cari = v.get("cari")
    bas = v.get("bas") or bugun.replace(day=1)
    bit = v.get("bit") or bugun
    if bas > bit:
        bas, bit = bit, bas
        hata = hata or "Başlangıç, bitişten sonraydı; tarihler yer değiştirdi."
    sekil = v.get("sekil") or ""

    if liste == "yapilan":
        veri = ol.yapilan_odemeler(bas, bit, cari, sekil)
        xlsx, ad = ol.yapilan_odemeler_xlsx, f"yapilan_odemeler_{bas:%Y%m%d}_{bit:%Y%m%d}.xlsx"
    else:
        veri = ol.odenecekler(bugun, cari)
        xlsx, ad = ol.odenecekler_xlsx, f"odenecekler_{bugun:%Y%m%d}.xlsx"

    if v.get("indir") == "xlsx":
        yanit = HttpResponse(xlsx(veri), content_type=
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        yanit["Content-Disposition"] = f'attachment; filename="{ad}"'
        return yanit

    sorgu = request.GET.copy()
    sorgu.pop("indir", None)
    return render(request, "defter/odeme_listesi.html", {
        "liste": liste, "veri": veri, "cari": cari, "cariler": Cari.objects.all(), "sekil": sekil,
        "sekiller": Belge.OdemeSekli.choices, "bas": bas, "bit": bit, "hata": hata, "bugun": bugun,
        "kova_etiketleri": ol.KOVA_ETIKETLERI, "excel_sorgu": sorgu.urlencode(), "sayfa": "odemeler",
    })


@yonetici_gerekli
def yedek_sayfasi(request):
    from django.conf import settings

    from . import yedek as yd
    from .models import YedekKaydi
    hedefler = [str(h) for h in settings.YEDEK_DIZINLERI]
    ayni_disk = [h for h in hedefler if yd.ayni_disk_mi(h, settings.VERI_DIZINI)]
    return render(request, "defter/yedek.html", {
        "hedefler": hedefler, "ayni_disk": ayni_disk, "durum": yd.yedek_durumu(),
        "kayitlar": YedekKaydi.objects.all()[:30], "sayfa": "yedek",
        "gunluk": settings.YEDEK_GUNLUK_SAKLA, "aylik": settings.YEDEK_AYLIK_SAKLA,
    })


@yonetici_gerekli
@require_POST
def yedek_al(request):
    from . import yedek as yd
    try:
        for k in yd.yedekle():
            if k.durum == "HATA":
                messages.error(request, f"{k.hedef}: yedek BAŞARISIZ — {k.ayrinti}")
            elif k.durum == "UYARI":
                messages.warning(request, f"{k.hedef}: yedek alındı ama uyarı var — {k.ayrinti}")
            else:
                messages.success(request, f"{k.hedef}: yedek alındı, doğrulandı, geri yükleme testi geçti ({k.dosya}).")
    except yd.YedekHatasi as e:
        messages.error(request, str(e))
    return redirect("yedek_sayfasi")


@yonetici_gerekli
def gunluk_sayfasi(request):
    from datetime import date as _date

    from django.core.paginator import Paginator
    from django.db.models import Q

    from .models import IslemGunlugu
    qs = IslemGunlugu.objects.all()
    f = {k: request.GET.get(k, "").strip() for k in ("q", "kullanici", "model", "islem", "bas", "bit", "nesne")}
    if f["q"]:
        qs = qs.filter(Q(nesne_ozeti__icontains=f["q"]) | Q(ayrinti__icontains=f["q"]) | Q(model__icontains=f["q"]))
    if f["kullanici"]:
        qs = qs.filter(kullanici=f["kullanici"])
    if f["model"]:
        qs = qs.filter(model=f["model"])
    if f["islem"] in IslemGunlugu.Islem.values:
        qs = qs.filter(islem=f["islem"])
    if f["nesne"].isdigit():
        qs = qs.filter(nesne_id=int(f["nesne"]))
    for anahtar, op in (("bas", "zaman__date__gte"), ("bit", "zaman__date__lte")):
        try:
            if f[anahtar]:
                qs = qs.filter(**{op: _date.fromisoformat(f[anahtar])})
        except ValueError:
            f[anahtar] = ""
    sayfa = Paginator(qs, 50).get_page(request.GET.get("sayfa"))
    sorgu = request.GET.copy()
    sorgu.pop("sayfa", None)
    return render(request, "defter/gunluk.html", {
        "sayfa_nesnesi": sayfa, "filtre": f, "sorgu": sorgu.urlencode(), "sayfa": "gunluk",
        "kullanicilar": IslemGunlugu.objects.order_by().values_list("kullanici", flat=True).distinct(),
        "modeller": IslemGunlugu.objects.order_by().exclude(model="").values_list("model", flat=True).distinct(),
        "islemler": IslemGunlugu.Islem.choices,
    })
