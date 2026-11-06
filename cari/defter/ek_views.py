from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import ek_servisi as es
from .models import Ek
from .views import giris_gerekli


def sahip_etiketi(sahip) -> str:
    return {"Belge": lambda s: f"{s.get_tur_display()} · {s.cari} · {s.tarih:%d.%m.%Y}"
                               f"{' · ' + s.evrak_no if s.evrak_no else ''}",
            "KasaHareketi": lambda s: f"Kasa hareketi · {s.hesap} · {s.tarih:%d.%m.%Y} · {s.get_yon_display()}",
            "EkstreMutabakat": lambda s: f"Ekstre mutabakatı · {s.cari} · {s.ekstre_tarihi:%d.%m.%Y}",
            "Cari": lambda s: f"Cari · {s.unvan}"}[type(sahip).__name__](sahip)


def sahip_geri_url(tur, sahip) -> str:
    return {"belge": lambda: reverse("cari_ekstre", args=[sahip.cari_id]),
            "kasa": lambda: f"{reverse('kasa')}?hesap={sahip.hesap_id}",
            "mutabakat": lambda: reverse("mutabakat_detay", args=[sahip.pk]),
            "cari": lambda: reverse("cari_ekstre", args=[sahip.pk])}[tur]()


def _sahip_al(tur, pk):
    model = es.SAHIPLER.get(tur)
    if model is None:
        raise Http404
    return get_object_or_404(model, pk=pk)


@giris_gerekli
def ek_sahip(request, tur, pk):
    sahip = _sahip_al(tur, pk)
    if request.method == "POST":
        dosyalar = request.FILES.getlist("dosyalar")
        if not dosyalar:
            messages.error(request, "Dosya seçilmedi.")
        elif len(dosyalar) > settings.EK_MAX_ADET:
            messages.error(request, f"Tek seferde en fazla {settings.EK_MAX_ADET} dosya yüklenebilir.")
        else:
            eklenen = 0
            for d in dosyalar:
                try:
                    es.ek_ekle(sahip, d, request.POST.get("aciklama", ""), request.user.get_username())
                    eklenen += 1
                except es.EkHatasi as e:
                    messages.error(request, str(e))
            if eklenen:
                messages.success(request, f"{eklenen} dosya eklendi.")
        return redirect(request.path)
    return render(request, "defter/ek_sahip.html", {
        "tur": tur, "sahip": sahip, "etiket": sahip_etiketi(sahip), "geri": sahip_geri_url(tur, sahip),
        "ekler": es.ekleri_listele(sahip), "kaldirilanlar": es.ekleri_listele(sahip, True).filter(kaldirildi=True),
        "izinli": es.izinli_uzantilar(), "maks_mb": settings.EK_MAX_BAYT // (1024 * 1024),
        "gorsel_turleri": es.GORSEL, "sayfa": "ekler",
    })


@giris_gerekli
def ek_indir(request, pk):
    ek = get_object_or_404(Ek, pk=pk, kaldirildi=False)
    yol = es.depo_yolu(ek)
    if not yol.is_file():
        raise Http404("Dosya depoda bulunamadı. 'python manage.py ekleri_dogrula' ile kontrol edin.")
    indir = request.GET.get("indir") == "1" or ek.icerik_turu not in es.ONIZLENEBILIR
    yanit = FileResponse(open(yol, "rb"), content_type=ek.icerik_turu, as_attachment=indir,
                         filename=ek.orijinal_ad)
    yanit["X-Content-Type-Options"] = "nosniff"
    yanit["Cache-Control"] = "private, no-store"
    return yanit


@giris_gerekli
@require_POST
def ek_kaldir(request, pk):
    ek = get_object_or_404(Ek, pk=pk)
    try:
        es.ek_kaldir(ek, request.POST.get("neden", ""))
        messages.success(request, "Ek kaldırıldı (dosya diskte saklanmaya devam eder).")
    except es.EkHatasi as e:
        messages.error(request, str(e))
    return redirect("ek_sahip", tur=ek.sahip_kisa, pk=ek.sahip.pk)


@giris_gerekli
def ek_depo(request):
    qs = Ek.objects.select_related("belge__cari", "kasa_hareketi__hesap", "mutabakat__cari", "cari")
    f = {k: request.GET.get(k, "").strip() for k in ("q", "tur", "bas", "bit", "kaldirilan")}
    if f["kaldirilan"] != "1":
        qs = qs.filter(kaldirildi=False)
    if f["q"]:
        qs = qs.filter(Q(orijinal_ad__icontains=f["q"]) | Q(aciklama__icontains=f["q"])
                       | Q(belge__evrak_no__icontains=f["q"]) | Q(belge__cari__unvan__icontains=f["q"])
                       | Q(cari__unvan__icontains=f["q"]) | Q(mutabakat__cari__unvan__icontains=f["q"]))
    alan = {"belge": "belge", "kasa": "kasa_hareketi", "mutabakat": "mutabakat", "cari": "cari"}.get(f["tur"])
    if alan:
        qs = qs.filter(**{f"{alan}__isnull": False})
    from datetime import date
    for anahtar, op in (("bas", "yuklenme__date__gte"), ("bit", "yuklenme__date__lte")):
        try:
            if f[anahtar]:
                qs = qs.filter(**{op: date.fromisoformat(f[anahtar])})
        except ValueError:
            f[anahtar] = ""
    aktif = Ek.objects.filter(kaldirildi=False)
    sayfa = Paginator(qs, 40).get_page(request.GET.get("sayfa"))
    sorgu = request.GET.copy()
    sorgu.pop("sayfa", None)
    return render(request, "defter/ek_depo.html", {
        "sayfa_nesnesi": sayfa, "filtre": f, "sorgu": sorgu.urlencode(),
        "adet": aktif.count(), "toplam_bayt": aktif.aggregate(t=Sum("boyut_bayt"))["t"] or 0,
        "sayfa": "ekler",
    })
