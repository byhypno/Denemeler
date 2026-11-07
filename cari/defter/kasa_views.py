from datetime import date

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import ek_servisi as es
from . import metin
from . import kasa_rapor as kr
from . import kasa_servisi as ks
from .fields import kurus_bicimle
from .forms import GunSonuForm, KasaHareketiForm
from .models import GunSonu, KasaHareketi, KasaKategori
from .views import AYLAR
from .yetki import gorunur_kasalar, yetki_gerekli


def _hesap_veya_yok(request, hesap_id):
    """
    Kullanıcının GÖREBİLDİĞİ kasalar arasından seçer (ör. Kasiyer yalnızca Ofis Kasa).
    Var olan ama görme yetkisi olmayan bir kasa AÇIKÇA istenirse 403: sessizce başka kasaya düşmek,
    kullanıcının kaydı yanlış kasaya girmesine yol açardı.
    """
    gorunur = gorunur_kasalar(request.user)
    hid = metin.guvenli_int(hesap_id)
    if hid is not None and not gorunur.filter(pk=hid).exists():
        if ks.Hesap.objects.filter(pk=hid).exists() and request.method == "POST":
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

    # --- Hareket listesi + filtreler (ekran ve Excel aynı süzgeci kullanır)
    qs, f = ks.hareket_sorgusu(hesap, request.GET)
    liste_toplami = ks.sorgu_toplami(qs)
    if request.GET.get("indir") == "xlsx":
        yanit = HttpResponse(ks.hareketler_xlsx(hesap, qs),
                             content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        yanit["Content-Disposition"] = f'attachment; filename="ofis_kasa_hareketler_{bugun:%Y%m%d}.xlsx"'
        return yanit
    sayfa = Paginator(qs, 40).get_page(request.GET.get("sayfa"))
    sorgu = request.GET.copy()
    sorgu.pop("sayfa", None)
    sorgu.pop("indir", None)

    aylik = ks.kasa_aylik(hesap, yil, bugun)
    dagilim = ks.kategori_dagilimi(hesap, yil)
    ozet = ks.kasa_ozeti(hesap, bugun)
    return render(request, "defter/kasa.html", {
        "hesap": hesap, "hesaplar": gorunur_kasalar(request.user), "harcayanlar": ks.harcayanlar(hesap),
        "form": form, "ozet": ozet, "liste_toplami": liste_toplami, "kdv_alanlari": ["kdv_modu", "kdv_orani", "tevkifat_orani"], "yil_cikis": sum(aylik["cikis"]),
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


@yetki_gerekli("kasa_goruntule")
def kasa_rapor(request):
    """Ofis Kasa raporu: ekranda önizleme; ?indir=xlsx|pdf ile dosya. Dönem: bu ay / önceki ay / son para girişinden / bu yıl / özel."""
    hesap = _hesap_veya_yok(request, request.GET.get("hesap"))
    if hesap is None:
        return render(request, "defter/kasa_rapor.html", {"hesap": None, "sayfa": "kasa"})
    bugun = date.today()
    bas, bit, etiket = kr.donem_sec(hesap, request.GET, bugun)
    r = kr.kasa_raporu(hesap, bas, bit)
    indir = request.GET.get("indir")
    if indir in ("xlsx", "pdf"):
        if indir == "xlsx":
            icerik, tur = kr.rapor_xlsx(r), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            icerik, tur = kr.rapor_pdf(r), "application/pdf"
        yanit = HttpResponse(icerik, content_type=tur)
        yanit["Content-Disposition"] = f'attachment; filename="{kr.dosya_adi(r, indir)}"'
        return yanit
    return render(request, "defter/kasa_rapor.html", {
        "hesap": hesap, "r": r, "etiket": etiket, "sayfa": "kasa", "bugun": bugun,
        "donemler": [("bu_ay", "Bu ay"), ("onceki_ay", "Önceki ay"), ("son_giris", "Son para girişinden bugüne"), ("yil", "Bu yıl")],
        "sorgu": f"hesap={hesap.pk}&bas={bas.isoformat()}&bit={bit.isoformat()}",
    })


@yetki_gerekli("kasa_yaz")
def kasa_harcayan_duzelt(request):
    """Harcayan adını toplu düzeltir (yazım farkları, boş harcayanı doldurma). Kapalı günlerdeki kayıtlara dokunmaz."""
    hesap = _hesap_veya_yok(request, request.POST.get("hesap") or request.GET.get("hesap"))
    if hesap is None:
        return redirect("kasa")
    ozet = []
    sayac = {}
    for h in hesap.hareketler.filter(iptal=False):
        ad = h.harcayan or "-"
        k = metin.katla(ad) if ad != "-" else "-"
        sayac.setdefault(k, {"ad": ad, "adet": 0, "adlar": set()})
        sayac[k]["adet"] += 1
        sayac[k]["adlar"].add(ad)
    for k, v in sayac.items():
        v["varyant"] = len(v["adlar"]) > 1
        ozet.append(v)
    ozet.sort(key=lambda v: (v["ad"] != "-", metin.katla(v["ad"])))
    if request.method == "POST":
        try:
            sonuc = ks.harcayan_duzelt(hesap, request.POST.get("eski", ""), request.POST.get("yeni", ""))
        except ValidationError as e:
            messages.error(request, _hata_metni(e))
        else:
            mesaj = f"{sonuc['degisen']} kayıtta harcayan düzeltildi."
            if sonuc["kilitli"]:
                mesaj += f" {sonuc['kilitli']} kayıt kapalı güne ait olduğu için değiştirilmedi."
            messages.success(request, mesaj)
        return redirect(f"{reverse('kasa_harcayan_duzelt')}?hesap={hesap.pk}")
    return render(request, "defter/kasa_harcayan.html", {"hesap": hesap, "satirlar": ozet, "sayfa": "kasa",
                                                          "hesaplar": gorunur_kasalar(request.user)})
