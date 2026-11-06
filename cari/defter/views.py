from datetime import date

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from . import ek_servisi as es
from . import odeme_listesi as ol
from . import services
from .models import Belge, Cari, EkstreMutabakat

AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
giris_gerekli = staff_member_required(login_url="/admin/login/")


@giris_gerekli
def dashboard(request):
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
    return render(request, "defter/dashboard.html", {
        "yil": yil, "yillar": yillar, "cari": cari, "cariler": Cari.objects.all(),
        "guncel_borc": guncel_borc, "yil_alis": sum(aylik["alis"]),
        "yil_odeme": sum(aylik["odeme"]), "yil_iade": sum(aylik["iade"]),
        "acik_fark": acik_fark, "kontrol": kontrol, "yas": yas, "borclular": borclular,
        "grafik": grafik, "veri_var": Belge.objects.filter(iptal=False).exists(),
        "bugun": bugun, "sayfa": "dashboard",
    })


@giris_gerekli
def mutabakat_liste(request):
    ozetler = [services.mutabakat_ozeti(m) for m in
               EkstreMutabakat.objects.select_related("cari")]
    return render(request, "defter/mutabakat_liste.html", {"ozetler": ozetler, "sayfa": "mutabakat"})


@giris_gerekli
def mutabakat_detay(request, pk):
    m = get_object_or_404(EkstreMutabakat.objects.select_related("cari"), pk=pk)
    return render(request, "defter/mutabakat_detay.html",
                  {"oz": services.mutabakat_ozeti(m), "sayfa": "mutabakat",
                   "ek_sayisi": m.ekler.filter(kaldirildi=False).count()})


class _Donem(forms.Form):
    bas = forms.DateField(required=False)
    bit = forms.DateField(required=False)


@giris_gerekli
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
    return render(request, "defter/ekstre.html", {
        "ek_sayi": es.ek_sayilari([b.pk for b, _ in satirlar], "belge"),
        "cari_ek_sayisi": cari.ekler.filter(kaldirildi=False).count(),
        "cari": cari, "onceki": onceki, "satirlar": satirlar, "kapanis": kapanis,
        "bas": bas, "bit": bit, "hata": hata, "sayfa": "ekstre",
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


@giris_gerekli
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
