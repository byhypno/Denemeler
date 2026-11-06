from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import ek_servisi as es
from . import kasa_servisi as ks
from .fields import kurus_bicimle
from .forms import GunSonuForm, KasaHareketiForm
from .models import GunSonu, KasaHareketi, KasaKategori
from .views import AYLAR
from .yetki import gorunur_kasalar, oturum_gerekli, var_mi, yetki_gerekli


def _hesap_veya_yok(request, hesap_id):
    """
    Kullanıcının GÖREBİLDİĞİ kasalar arasından seçer (ör. Kasiyer yalnızca Ofis Kasa).
    Var olan ama görme yetkisi olmayan bir kasa AÇIKÇA istenirse 403: sessizce başka kasaya düşmek,
    kullanıcının kaydı yanlış kasaya girmesine yol açardı.
    """
    gorunur = gorunur_kasalar(request.user)
    if hesap_id and str(hesap_id).isdigit() and not gorunur.filter(pk=int(hesap_id)).exists():
        if ks.Hesap.objects.filter(pk=int(hesap_id)).exists() and request.method == "POST":
            # Pasif kasayı GÖRÜNTÜLEMEK varsayılan kasaya düşer; ama YAZMA asla başka kasaya düşmez (yanlış kasaya kayıt olmasın)
            raise PermissionDenied("Bu kasa kapalı; kayıt buradan girilemez.")
    return ks.varsayilan_hesap(hesap_id, hesaplar=gorunur)


def _hata_metni(e: ValidationError) -> str:
    return " ".join(e.messages)


@yetki_gerekli("kasa_goruntule", "kasa_yaz")
def kasa_ana(request):
    bugun = date.today()
    hesap = _hesap_veya_yok(request, request.GET.get("hesap"))
    if hesap is None:
        return render(request, "defter/kasa.html", {"hesap": None, "sayfa": "kasa"})

    if request.method == "POST":
        form = KasaHareketiForm(request.POST, hesap=hesap)
        if form.is_valid():
            h = form.save()
            messages.success(request, f"Kaydedildi: {h.get_yon_display()} {kurus_bicimle(h.tutar_kurus)} ₺")
            return redirect(f"{reverse('kasa')}?hesap={hesap.pk}")
    else:
        form = KasaHareketiForm(hesap=hesap, initial={"tarih": bugun, "yon": KasaHareketi.Yon.CIKIS})

    yillar = ks.kasa_yillari(hesap, bugun)
    try:
        yil = int(request.GET.get("yil", ""))
    except ValueError:
        yil = yillar[-1]
    if yil not in yillar:
        yil = yillar[-1]

    # --- Hareket listesi + filtreler
    qs = hesap.hareketler.select_related("kategori").order_by("-tarih", "-id")
    f = {k: request.GET.get(k, "") for k in ("bas", "bit", "yon", "kategori", "iptal")}
    for alan, op in (("bas", "tarih__gte"), ("bit", "tarih__lte")):
        try:
            if f[alan]:
                qs = qs.filter(**{op: date.fromisoformat(f[alan])})
        except ValueError:
            f[alan] = ""
    if f["yon"] in ("GIRIS", "CIKIS"):
        qs = qs.filter(yon=f["yon"])
    if f["kategori"].isdigit():
        qs = qs.filter(kategori_id=int(f["kategori"]))
    if f["iptal"] != "1":
        qs = qs.filter(iptal=False)
    sayfa = Paginator(qs, 40).get_page(request.GET.get("sayfa"))
    sorgu = request.GET.copy()
    sorgu.pop("sayfa", None)

    aylik = ks.kasa_aylik(hesap, yil, bugun)
    dagilim = ks.kategori_dagilimi(hesap, yil)
    ozet = ks.kasa_ozeti(hesap, bugun)
    return render(request, "defter/kasa.html", {
        "hesap": hesap, "hesaplar": gorunur_kasalar(request.user),
        "form": form, "ozet": ozet, "kdv_alanlari": ["kdv_modu", "kdv_orani", "tevkifat_orani"], "yil_cikis": sum(aylik["cikis"]),
        "yil": yil, "yillar": yillar, "filtre": f, "sayfa_nesnesi": sayfa, "sorgu": sorgu.urlencode(),
        "bakiyeler": ks.hareketler_bakiyeli(hesap), "kategoriler": KasaKategori.objects.filter(aktif=True),
        "en_buyuk": ks.en_buyuk_cikislar(hesap, yil),
        "kilit_siniri": ozet["kilit_siniri"],
        "grafik": {"aylar": AYLAR, **aylik, "kat_etiket": [a for a, _ in dagilim],
                   "kat_deger": [t for _, t in dagilim]},
        "sayfa": "kasa", "bugun": bugun,
        "ek_sayi": es.ek_sayilari([h.pk for h in sayfa.object_list], "kasa_hareketi"),
    })


@yetki_gerekli("kasa_yaz")
@require_POST
def kasa_hareket_iptal(request, pk):
    h = get_object_or_404(KasaHareketi, pk=pk)
    if not gorunur_kasalar(request.user).filter(pk=h.hesap_id).exists():
        raise PermissionDenied("Bu kasaya erişim yetkiniz yok.")
    neden = request.POST.get("neden", "").strip()
    if not neden:
        messages.error(request, "İptal için neden yazın.")
    elif h.iptal:
        messages.info(request, "Kayıt zaten iptal edilmiş.")
    else:
        h.iptal, h.iptal_nedeni = True, neden[:250]
        try:
            h.full_clean()
            h.save()
            messages.success(request, "Kayıt iptal edildi.")
        except ValidationError as e:
            messages.error(request, _hata_metni(e))
    return redirect(f"{reverse('kasa')}?hesap={h.hesap_id}")


@yetki_gerekli("kasa_goruntule", "kasa_yaz")
def kasa_gun_sonu(request):
    bugun = date.today()
    hesap = _hesap_veya_yok(request, request.GET.get("hesap"))
    if hesap is None:
        return render(request, "defter/kasa_gun_sonu.html", {"hesap": None, "sayfa": "kasa"})
    if request.method == "POST":
        form = GunSonuForm(request.POST)
        if form.is_valid():
            try:
                g = ks.gun_sonu_kapat(hesap, form.cleaned_data["tarih"], form.cleaned_data["sayilan"],
                                      form.cleaned_data["aciklama"], form.cleaned_data["farki_isle"], bugun)
            except ValidationError as e:
                form.add_error(None, _hata_metni(e))
            else:
                messages.success(request, f"{g.tarih:%d.%m.%Y} kapatıldı. Fark: {kurus_bicimle(g.fark_kurus)} ₺")
                return redirect(f"{reverse('kasa_gun_sonu')}?hesap={hesap.pk}")
        secili = form["tarih"].value()
    else:
        secili = request.GET.get("tarih") or bugun.isoformat()
        form = GunSonuForm(initial={"tarih": secili})
    try:
        secili_tarih = date.fromisoformat(str(secili))
    except ValueError:
        secili_tarih = bugun
    return render(request, "defter/kasa_gun_sonu.html", {
        "hesap": hesap, "form": form, "secili_tarih": secili_tarih,
        "hesaplar": gorunur_kasalar(request.user),
        "beklenen": ks.gun_sonu_beklenen(hesap, secili_tarih),
        "kilit_siniri": hesap.kilit_siniri(), "acik_gunler": ks.acik_gunler(hesap, bugun),
        "kapanislar": GunSonu.objects.filter(hesap=hesap)[:30], "sayfa": "kasa",
    })
