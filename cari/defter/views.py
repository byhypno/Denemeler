from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.db import IntegrityError
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import ek_servisi as es
from . import odeme_listesi as ol
from . import gider_servisi, kasa_servisi as ks, malzeme_servisi, metin, services, trend
from .fields import kurus_bicimle
from .forms import GIRILEBILIR_TURLER, BelgeDuzeltForm, BelgeForm, CariForm
from .models import Belge, Cari, EkstreMutabakat
from .yetki import oturum_gerekli, var_mi, yetki_gerekli

def _cariler(**filtre):
    """Seçici kutuları için cariler, TÜRKÇE alfabe sırasıyla (SQLite ikili sıralaması Ç/Ö/Ş/İ/Ü'yü Z'den sonraya atar)."""
    return metin.turkce_sirala(Cari.objects.filter(**filtre), lambda c: c.unvan)


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
    if metin.guvenli_int(cari_id) is not None:
        cari = Cari.objects.filter(pk=metin.guvenli_int(cari_id)).first()

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
    # Ofis içi göstergeler (cari filtresinden bağımsız): kasa bakiyesi ve bu ayın net genel gideri
    kasa_bakiye = None
    if var_mi(request.user, "kasa_goruntule"):
        kasa = ks.varsayilan_hesap()
        kasa_bakiye = kasa.bakiye_kurus() if kasa else None
    gider_ay = gider_servisi.ay_toplami(bugun.year, bugun.month)
    takvim = {g["anahtar"]: g for g in services.odeme_takvimi(bugun, cari)["gruplar"]}
    degisimler = {ad: trend.degisim(aylik[ad], yil, bugun) for ad in ("alis", "odeme", "iade", "ay_sonu")}
    return render(request, "defter/dashboard.html", {
        "yil": yil, "aylik": aylik, "degisimler": degisimler, "takvim": takvim, "yillar": yillar, "cari": cari, "cariler": _cariler(),
        "guncel_borc": guncel_borc, "yil_alis": sum(aylik["alis"]),
        "yil_odeme": sum(aylik["odeme"]), "yil_iade": sum(aylik["iade"]),
        "acik_fark": acik_fark, "kontrol": kontrol, "yas": yas, "borclular": borclular,
        "grafik": grafik, "veri_var": Belge.objects.filter(iptal=False).exists(),
        "bugun": bugun, "sayfa": "dashboard",
        "kasa_bakiye": kasa_bakiye, "gider_ay": gider_ay,
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
        "bas": bas, "bit": bit, "hata": hata, "sayfa": "tedarikciler", "aylar": aylar, "eksi_ay": eksi_ay,
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
        "liste": liste, "veri": veri, "cari": cari, "cariler": _cariler(), "sekil": sekil,
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
    if metin.guvenli_int(f["nesne"]) is not None:
        qs = qs.filter(nesne_id=metin.guvenli_int(f["nesne"]))
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


SIRALAR = {"borc": "Borca göre", "unvan": "Ada göre", "son": "Son hareket"}


@yetki_gerekli("goruntule")
def tedarikciler(request):
    """Tedarikçi kartları: arama, durum süzgeci, sıralama. Karta tıklayınca ekstre açılır."""
    q = request.GET.get("q", "").strip()
    sira = request.GET.get("sira", "borc")
    sira = sira if sira in SIRALAR else "borc"
    pasifler = request.GET.get("pasif") == "1"
    son = dict(Belge.objects.filter(iptal=False).values("cari").annotate(t=Max("tarih")).values_list("cari", "t"))
    satirlar = []
    for c, bakiye in services.cari_bakiyeleri():
        if not pasifler and not c.aktif:
            continue
        if not metin.eslesir(q, c.unvan, c.kisa_kod, c.vergi_bilgisi, c.yetkili, c.telefon, c.eposta):
            continue
        satirlar.append({"cari": c, "bakiye": bakiye, "son": son.get(c.pk)})
    if sira == "unvan":
        satirlar.sort(key=lambda r: metin.katla(r["cari"].unvan))
    elif sira == "son":
        satirlar.sort(key=lambda r: r["son"] or date.min, reverse=True)
    toplam_borc = sum(r["bakiye"] for r in satirlar if r["bakiye"] > 0)
    return render(request, "defter/tedarikciler.html", {
        "satirlar": satirlar, "q": q, "sira": sira, "siralar": SIRALAR, "pasifler": pasifler,
        "toplam_borc": toplam_borc, "toplam_cari": Cari.objects.count(), "sayfa": "tedarikciler",
    })


@yetki_gerekli("veri_gir")
def tedarikci_form(request, pk=None):
    """Tedarikçi ekle (pk yok) veya düzenle. Kayıt işlem günlüğüne düşer; silme yoktur (pasif yapılır)."""
    cari = get_object_or_404(Cari, pk=pk) if pk else None
    form = CariForm(request.POST or None, instance=cari)
    if not pk:
        del form.fields["aktif"]
        if request.method != "POST":
            form.initial.setdefault("acilis_tarih", date.today())
    else:
        for ad in ("acilis_tutar", "acilis_yon", "acilis_tarih"):         # açılış bakiyesi yalnızca ilk kayıtta; sonra ekstreden hareket girilir
            del form.fields[ad]
    if request.method == "POST" and form.is_valid():
        kayit = form.save()
        messages.success(request, f"{kayit.unvan} {'güncellendi' if pk else 'eklendi'}.")
        return redirect("cari_ekstre", pk=kayit.pk) if not pk else redirect("tedarikciler")
    return render(request, "defter/tedarikci_form.html", {"form": form, "cari": cari, "sayfa": "tedarikciler"})


@yetki_gerekli("goruntule")
def odeme_takvimi(request):
    """Vadesi geçen ve yaklaşan borçlar: 'bu hafta kime ne ödeyeceğiz'. Çıktısı yazdırılabilir."""
    bugun = date.today()
    cari = None
    if metin.guvenli_int(request.GET.get("cari")) is not None:
        cari = Cari.objects.filter(pk=metin.guvenli_int(request.GET["cari"])).first()
    t = services.odeme_takvimi(bugun, cari)
    return render(request, "defter/odeme_takvimi.html", {
        "t": t, "bugun": bugun, "cari": cari, "cariler": _cariler(aktif=True), "sayfa": "takvim",
        "g": {g["anahtar"]: g for g in t["gruplar"]},
    })


@yetki_gerekli("veri_gir")
def belge_yeni(request, pk):
    """Cari ekstresinden yeni hareket. `?tur=ODEME|ALIS_FISI|...` türü önceden seçer."""
    cari = get_object_or_404(Cari, pk=pk)
    tur = request.GET.get("tur", "")
    gecerli = {t.value for t in GIRILEBILIR_TURLER}
    if request.method == "POST":
        form = BelgeForm(request.POST, cari=cari)
        b = None
        if form.is_valid():
            try:
                b = form.save()
            except IntegrityError:           # aynı evrak no'nun eşzamanlı çift gönderimi: veritabanı kısıtı son söz
                form.add_error("evrak_no", "Bu evrak numarası az önce başka bir kayıtla girildi.")
        if b is not None:
            messages.success(request, f"Kaydedildi: {b.get_tur_display()} · {kurus_bicimle(b.tutar_kurus)} ₺ ({cari.unvan}).")
            for u in malzeme_servisi.zam_uyarilari(form.olusan_kalemler):          # fiyat hafızası: önceki alışa göre ZAM
                messages.warning(request, f"Zam: {u['malzeme'].ad} {kurus_bicimle(round(u['onceki']))} ₺ → {kurus_bicimle(round(u['yeni']))} ₺ "
                                          f"(%{malzeme_servisi.yuzde_metni(u['yuzde'])} arttı; önceki alış {u['onceki_tarih']:%d.%m.%Y}, {u['onceki_cari']}).")
            if "_yenisi" in request.POST:
                return redirect(f"{reverse('belge_yeni', args=[cari.pk])}?tur={b.tur}")
            return redirect("cari_ekstre", pk=cari.pk)
    else:
        form = BelgeForm(cari=cari, initial={"tarih": date.today(), "tur": tur if tur in gecerli else Belge.Tur.ALIS_FISI})
    satirlar = list(form.kalem_satirlari) if request.method == "POST" else []
    satirlar += [{k: "" for k in BelgeForm.ALANLAR} for _ in range(max(0, 8 - len(satirlar)))]      # en az 8 satır görünür
    return render(request, "defter/belge_form.html", {
        "form": form, "cari": cari, "kalem_satirlari": list(enumerate(satirlar)), "kdv_alanlari": ["kdv_modu", "kdv_orani", "tevkifat_orani"], "sayfa": "tedarikciler",
        "yinelenme": getattr(form, "yinelenme", False), "hafiza": malzeme_servisi.hafiza_verisi(),
    })


@yetki_gerekli("veri_gir")
def belge_duzelt(request, pk):
    """Var olan cari hareketini düzeltir (tür ve cari değişmez). İptal edilmiş kayıt düzeltilemez. Değişiklik işlem günlüğüne yazılır."""
    belge = get_object_or_404(Belge.objects.select_related("cari"), pk=pk)
    if belge.iptal:
        messages.error(request, "İptal edilmiş kayıt düzeltilemez.")
        return redirect("cari_ekstre", pk=belge.cari_id)
    form = BelgeDuzeltForm(request.POST or None, belge=belge)
    if request.method == "POST" and form.is_valid():
        try:
            b = form.save()
        except IntegrityError:
            form.add_error("evrak_no", "Bu evrak numarası başka bir kayıtla çakışıyor.")
        else:
            messages.success(request, f"Düzeltildi: {b.get_tur_display()} · {kurus_bicimle(b.tutar_kurus)} ₺ ({belge.cari.unvan}).")
            for u in malzeme_servisi.zam_uyarilari(form.olusan_kalemler):
                messages.warning(request, f"Zam: {u['malzeme'].ad} {kurus_bicimle(round(u['onceki']))} ₺ → {kurus_bicimle(round(u['yeni']))} ₺ "
                                          f"(%{malzeme_servisi.yuzde_metni(u['yuzde'])} arttı; önceki alış {u['onceki_tarih']:%d.%m.%Y}, {u['onceki_cari']}).")
            return redirect("cari_ekstre", pk=belge.cari_id)
    satirlar = list(form.kalem_satirlari)
    satirlar += [{k: "" for k in BelgeForm.ALANLAR} for _ in range(max(0, 8 - len(satirlar)))]
    return render(request, "defter/belge_form.html", {
        "form": form, "cari": belge.cari, "belge": belge, "duzenle": True, "kalem_satirlari": list(enumerate(satirlar)),
        "kdv_alanlari": ["kdv_modu", "kdv_orani", "tevkifat_orani"], "sayfa": "tedarikciler",
        "yinelenme": getattr(form, "yinelenme", False), "hafiza": malzeme_servisi.hafiza_verisi(),
    })


@yetki_gerekli("veri_gir")
@require_POST
def belge_iptal(request, pk):
    """Silme yok, iptal var: neden zorunlu, kayıt bakiyeden düşer, işlem günlüğüne yazılır."""
    b = get_object_or_404(Belge, pk=pk)
    neden = request.POST.get("neden", "").strip()
    if not neden:
        messages.error(request, "İptal için neden yazın.")
    elif b.iptal:
        messages.info(request, "Kayıt zaten iptal edilmiş.")
    else:
        b.iptal, b.iptal_nedeni = True, neden[:250]
        b.save()
        messages.success(request, f"İptal edildi: {b.get_tur_display()} {b.tarih:%d.%m.%Y}.")
    return redirect("cari_ekstre", pk=b.cari_id)


@yetki_gerekli("goruntule")
def aylik_rapor(request):
    """Ay sonu özeti: tedarikçiler, net genel gider, Ofis Kasa. Yazdır (PDF) ve Excel. Varsayılan: önceki tam ay."""
    from . import rapor_servisi as rs
    bugun = date.today()
    yil, ay = (bugun.year - 1, 12) if bugun.month == 1 else (bugun.year, bugun.month - 1)
    try:
        y, a = int(request.GET.get("yil", yil)), int(request.GET.get("ay", ay))
        if 2000 <= y <= 2100 and 1 <= a <= 12:
            yil, ay = y, a
    except ValueError:
        pass
    r = rs.aylik_rapor(yil, ay, kasa_dahil=var_mi(request.user, "kasa_goruntule"))
    if request.GET.get("indir") == "xlsx":
        yanit = HttpResponse(rs.rapor_xlsx(r), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        yanit["Content-Disposition"] = f'attachment; filename="aylik_ozet_{yil}_{ay:02d}.xlsx"'
        return yanit
    yillar = sorted({d.year for d in Belge.objects.filter(iptal=False).dates("tarih", "year")} | {bugun.year, yil})
    return render(request, "defter/aylik_rapor.html", {
        "r": r, "yil": yil, "ay": ay, "yillar": yillar, "aylar": list(enumerate(trend.AY_ADLARI, start=1)),
        "sayfa": "rapor", "bugun": bugun,
    })


@yetki_gerekli("veri_gir")
def veri_girisi(request):
    """Veri girişi merkezi: günlük işlerin hepsi tek yerden (yönetim paneli yalnızca gelişmiş işler için).
    ?cari=<id>&tur=ALIS_FISI|ODEME|IADE ile seçilen tedarikçi için hareket formuna yönlendirir."""
    cari_id, tur = metin.guvenli_int(request.GET.get("cari")), request.GET.get("tur", "")
    if cari_id is not None and Cari.objects.filter(pk=cari_id).exists():
        gecerli = {t.value for t in GIRILEBILIR_TURLER}
        return redirect(f"{reverse('belge_yeni', args=[cari_id])}?tur={tur if tur in gecerli else Belge.Tur.ALIS_FISI}")
    if request.GET.get("cari"):
        messages.error(request, "Önce tedarikçiyi seçin.")
    return render(request, "defter/veri_girisi.html", {
        "cariler": _cariler(aktif=True), "sayfa": "veri_girisi", "kasa_yaz": var_mi(request.user, "kasa_yaz"),
    })
