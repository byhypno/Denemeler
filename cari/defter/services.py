import calendar
from collections import defaultdict, deque
from datetime import date, timedelta

from django.db.models import Case, F, IntegerField, Sum, When

from .models import Belge, BelgeKalem, Cari, EkstreMutabakat


def _etkili_toplam():
    return Sum(
        Case(
            When(tur__in=Belge.ARTIRAN, then=F("tutar_kurus")),
            When(tur__in=Belge.AZALTAN, then=-F("tutar_kurus")),
            default=0,
            output_field=IntegerField(),
        )
    )


def bakiye_kurus(cari, tarih_kadar=None) -> int:
    """Cari borç bakiyesi (kuruş). Pozitif = tedarikçiye borçluyuz. İptal kayıtlar sayılmaz."""
    qs = Belge.objects.filter(cari=cari, iptal=False)
    if tarih_kadar:
        qs = qs.filter(tarih__lte=tarih_kadar)
    return qs.aggregate(t=_etkili_toplam())["t"] or 0


def ekstre(cari, baslangic=None, bitis=None):
    """Satır satır ekstre: (belge, bakiye_kurus) listesi + dönem başı bakiye."""
    onceki = 0
    if baslangic:
        qs0 = Belge.objects.filter(cari=cari, iptal=False, tarih__lt=baslangic)
        onceki = qs0.aggregate(t=_etkili_toplam())["t"] or 0
    qs = Belge.objects.filter(cari=cari, iptal=False)
    if baslangic:
        qs = qs.filter(tarih__gte=baslangic)
    if bitis:
        qs = qs.filter(tarih__lte=bitis)
    satirlar, bakiye = [], onceki
    for b in qs.order_by("tarih", "id"):
        bakiye += b.etki * b.tutar_kurus
        satirlar.append((b, bakiye))
    return onceki, satirlar


# ------------------------------------------------------------------ Dashboard hesapları
ALIS_TURLERI = (Belge.Tur.ALIS_FISI, Belge.Tur.ALIS_FATURASI)
KOVALAR = ("0–30 gün", "31–60 gün", "61–90 gün", "90+ gün")


def _kova(yas_gun: int) -> int:
    return 0 if yas_gun <= 30 else 1 if yas_gun <= 60 else 2 if yas_gun <= 90 else 3


def _cari_fifo(belgeler):
    """Tek carinin (tarih, id) sıralı belgeleri -> (açık kuyruk [[belge, kalan]], avans_kurus)."""
    kuyruk, avans = deque(), 0
    for b in belgeler:
        if b.etki > 0:
            tutar = b.tutar_kurus
            kapanan = min(avans, tutar)
            avans -= kapanan
            if tutar - kapanan > 0:
                kuyruk.append([b, tutar - kapanan])
        else:
            kalan = b.tutar_kurus
            while kalan and kuyruk:
                al = min(kalan, kuyruk[0][1])
                kuyruk[0][1] -= al
                kalan -= al
                if kuyruk[0][1] == 0:
                    kuyruk.popleft()
            avans += kalan
    return kuyruk, avans


def _belge_gruplari(cari=None):
    qs = Belge.objects.filter(iptal=False).select_related("cari").order_by("cari_id", "tarih", "id")
    if cari:
        qs = qs.filter(cari=cari)
    grup = defaultdict(list)
    for b in qs:
        grup[b.cari_id].append(b)
    return grup


def _kalem_sozlugu(b, kalan, bugun):
    yas = max((bugun - b.tarih).days, 0)
    vade, gecikmis = None, False
    if b.cari.vade_gun is not None:
        vade = b.tarih + timedelta(days=b.cari.vade_gun)
        gecikmis = vade < bugun
    return {"cari": b.cari, "belge": b, "kalan_kurus": kalan, "yas_gun": yas,
            "kova": _kova(yas), "vade_tarihi": vade, "gecikmis": gecikmis}


def acik_kalemler(bugun=None, cari=None):
    """
    Açık (ödenmemiş) kalemler — FIFO varsayımıyla.

    VARSAYIM: ödeme/iade en eski borca mahsup edilir (ödemeler tek tek faturaya bağlanmadığı için).
    Açık kalemlerin toplamı = cari bakiyesidir. Fazla ödeme (avans), sonraki alışlardan düşülür.
    Dönüş: (kalemler, avans_kurus)  kalem = dict(cari, belge, kalan_kurus, yas_gun, kova, vade_tarihi, gecikmis)
    """
    bugun = bugun or date.today()
    kalemler, avans_toplam = [], 0
    for belgeler in _belge_gruplari(cari).values():
        kuyruk, avans = _cari_fifo(belgeler)
        avans_toplam += avans
        kalemler.extend(_kalem_sozlugu(b, kalan, bugun) for b, kalan in kuyruk)
    return kalemler, avans_toplam


def cari_bazli_acik_borc(bugun=None, cari=None):
    """
    Her cari için açık borç özeti (ödeme listesi için):
    [{cari, toplam_kurus, kovalar[4], en_eski_tarih, en_eski_yas, kalem_sayisi, vade_tanimli, vadesi_gecmis_kurus}]
    ve ayrıca fazla ödeme (avans) olan cariler [(cari, avans_kurus)].
    """
    bugun = bugun or date.today()
    satirlar, avanslar = [], []
    for belgeler in _belge_gruplari(cari).values():
        kuyruk, avans = _cari_fifo(belgeler)
        c = belgeler[0].cari
        if avans:
            avanslar.append((c, avans))
        if not kuyruk:
            continue
        kalemler = [_kalem_sozlugu(b, kalan, bugun) for b, kalan in kuyruk]
        kovalar = [0, 0, 0, 0]
        for k in kalemler:
            kovalar[k["kova"]] += k["kalan_kurus"]
        en_eski = min(k["belge"].tarih for k in kalemler)
        vadeli = [k for k in kalemler if k["vade_tarihi"] is not None]
        satirlar.append({
            "cari": c, "toplam_kurus": sum(kovalar), "kovalar": kovalar, "en_eski_tarih": en_eski,
            "en_eski_yas": max((bugun - en_eski).days, 0), "kalem_sayisi": len(kalemler),
            "vade_tanimli": bool(vadeli),
            "vadesi_gecmis_kurus": sum(k["kalan_kurus"] for k in vadeli if k["gecikmis"]),
        })
    satirlar.sort(key=lambda r: -r["toplam_kurus"])
    return satirlar, sorted(avanslar, key=lambda x: -x[1])


def yaslandirma(bugun=None, cari=None) -> dict:
    kalemler, avans = acik_kalemler(bugun, cari)
    kovalar = [0, 0, 0, 0]
    for k in kalemler:
        kovalar[k["kova"]] += k["kalan_kurus"]
    vadeli = [k for k in kalemler if k["vade_tarihi"] is not None]
    return {
        "kovalar": kovalar, "etiketler": list(KOVALAR), "avans_kurus": avans,
        "toplam_acik_kurus": sum(kovalar),
        "vade_tanimli": bool(vadeli),
        "vadesi_gecmis_kurus": sum(k["kalan_kurus"] for k in vadeli if k["gecikmis"]),
        "en_eski": sorted(kalemler, key=lambda k: k["belge"].tarih)[:10],
    }


TAKVIM_GRUPLARI = (
    ("gecikmis", "Vadesi geçmiş", "hata"),
    ("hafta", "Bu hafta (0–7 gün)", "uyari"),
    ("ay", "8–30 gün içinde", "bilgi"),
    ("sonra", "30 günden sonra", ""),
    ("vadesiz", "Vadesi tanımsız", ""),
)


def takvim_grubu(vade, bugun) -> str:
    """Vade tarihine göre ödeme takvimi grubu. Vade bugünse 'hafta' (bugün ödenmeli, henüz gecikmemiş)."""
    if vade is None:
        return "vadesiz"
    gun = (vade - bugun).days
    if gun < 0:
        return "gecikmis"
    if gun <= 7:
        return "hafta"
    return "ay" if gun <= 30 else "sonra"


def odeme_takvimi(bugun=None, cari=None) -> dict:
    """Açık kalemleri VADEYE göre gruplar (vade = belge tarihi + carinin vade günü).

    Kalemler FIFO varsayımıyla açık kalan tutarlardır (bkz. acik_kalemler). Vadesi tanımsız cariler ayrı grupta
    toplanır; bunların vadesi bilinmediği için 'gecikmiş' sayılmaz. Dönüş:
    {"gruplar": [{"anahtar","ad","ton","kalemler","toplam"}], "toplam", "avans", "vadesiz_cari_sayisi"}
    """
    bugun = bugun or date.today()
    kalemler, avans = acik_kalemler(bugun, cari)
    kutu = {k: [] for k, _, _ in TAKVIM_GRUPLARI}
    for k in kalemler:
        k["gun_kaldi"] = (k["vade_tarihi"] - bugun).days if k["vade_tarihi"] else None
        kutu[takvim_grubu(k["vade_tarihi"], bugun)].append(k)
    gruplar = []
    for anahtar, ad, ton in TAKVIM_GRUPLARI:
        ks = sorted(kutu[anahtar], key=lambda k: (k["vade_tarihi"] or date.max, k["cari"].unvan, k["belge"].tarih, k["belge"].pk))
        gruplar.append({"anahtar": anahtar, "ad": ad, "ton": ton, "kalemler": ks, "toplam": sum(k["kalan_kurus"] for k in ks)})
    return {"gruplar": gruplar, "toplam": sum(g["toplam"] for g in gruplar), "avans": avans,
            "vadesiz_cari_sayisi": len({k["cari"].pk for k in kutu["vadesiz"]})}


def _ay_sonu(yil, ay):
    return date(yil, ay, calendar.monthrange(yil, ay)[1])


def aylik_ozet(yil: int, cari=None, bugun=None) -> dict:
    """Seçilen yılın aylık alış/iade/ödeme ve ay sonu bakiyesi (kuruş)."""
    bugun = bugun or date.today()
    qs = Belge.objects.filter(iptal=False)
    if cari:
        qs = qs.filter(cari=cari)
    onceki = qs.filter(tarih__lt=date(yil, 1, 1)).aggregate(t=_etkili_toplam())["t"] or 0
    alis, iade, odeme, diger = ([0] * 12 for _ in range(4))
    for tarih, tur, tutar in qs.filter(tarih__year=yil).values_list("tarih", "tur", "tutar_kurus"):
        i = tarih.month - 1
        if tur in ALIS_TURLERI:
            alis[i] += tutar
        elif tur == Belge.Tur.IADE:
            iade[i] += tutar
        elif tur == Belge.Tur.ODEME:
            odeme[i] += tutar
        else:  # devir ve düzeltmeler (işaretli)
            diger[i] += tutar if tur in Belge.ARTIRAN else -tutar
    bakiye, ay_sonu = onceki, []
    for i in range(12):
        bakiye += alis[i] - iade[i] - odeme[i] + diger[i]
        gelecek = (yil, i + 1) > (bugun.year, bugun.month)
        ay_sonu.append(None if gelecek else bakiye)
    return {"alis": alis, "iade": iade, "odeme": odeme, "diger": diger, "ay_sonu": ay_sonu,
            "onceki_bakiye": onceki}


def cari_bakiyeleri():
    """[(cari, bakiye_kurus)] — tüm cariler, bakiyeye göre çoktan aza."""
    toplamlar = dict(Belge.objects.filter(iptal=False).values("cari").annotate(t=_etkili_toplam())
                     .values_list("cari", "t"))
    sonuc = [(c, toplamlar.get(c.pk, 0) or 0) for c in Cari.objects.all()]
    return sorted(sonuc, key=lambda x: -x[1])


def en_cok_alinan_kalemler(yil: int, cari=None, n=10):
    qs = BelgeKalem.objects.filter(belge__iptal=False, belge__tur__in=ALIS_TURLERI,
                                   belge__tarih__year=yil)
    if cari:
        qs = qs.filter(belge__cari=cari)
    return list(qs.values("aciklama").annotate(toplam=Sum("tutar_kurus"))
                .order_by("-toplam")[:n].values_list("aciklama", "toplam"))


def mutabakat_ozeti(m: EkstreMutabakat) -> dict:
    satirlar = list(m.satirlar.select_related("belge"))
    bizim = bakiye_kurus(m.cari, tarih_kadar=m.ekstre_tarihi)
    fark = bizim - m.ekstre_bakiye_kurus
    aciklanan = sum(s.bakiye_farki_kurus for s in satirlar)
    farkli = [s for s in satirlar if s.durum != "UYUMLU"]
    return {
        "mutabakat": m, "satirlar": satirlar, "farkli_satirlar": farkli,
        "bizim_bakiye_kurus": bizim, "ekstre_bakiye_kurus": m.ekstre_bakiye_kurus,
        "fark_kurus": fark, "aciklanan_kurus": aciklanan,
        "aciklanamayan_kurus": fark - aciklanan,
    }


def son_mutabakatlar():
    """Her cari için en güncel ekstre mutabakatı."""
    gorulen, sonuc = set(), []
    for m in EkstreMutabakat.objects.select_related("cari").order_by("-ekstre_tarihi", "-id"):
        if m.cari_id not in gorulen:
            gorulen.add(m.cari_id)
            sonuc.append(m)
    return sonuc


def kontrol_listesi(bugun=None) -> dict:
    """Dikkat gerektiren kayıtlar."""
    bugun = bugun or date.today()
    # 1) Ay sonu bakiyesi eksiye düşen aylar (fazla ödeme / eksik kayıt belirtisi)
    eksi = []
    for cari in Cari.objects.all():
        belgeler = list(Belge.objects.filter(cari=cari, iptal=False).order_by("tarih", "id"))
        if not belgeler:
            continue
        bakiye, i = 0, 0
        y, a = belgeler[0].tarih.year, belgeler[0].tarih.month
        while (y, a) <= (bugun.year, bugun.month):
            ay_sonu = _ay_sonu(y, a)
            while i < len(belgeler) and belgeler[i].tarih <= ay_sonu:
                bakiye += belgeler[i].etki * belgeler[i].tutar_kurus
                i += 1
            if bakiye < 0:
                eksi.append({"cari": cari, "yil": y, "ay": a, "bakiye_kurus": bakiye})
            y, a = (y + 1, 1) if a == 12 else (y, a + 1)
    # 2) Aynı tedarikçi evrak numarası birden fazla belgede
    tekrar = []
    sayac = defaultdict(list)
    for b in Belge.objects.filter(iptal=False).exclude(harici_evrak_no="").select_related("cari"):
        sayac[(b.cari_id, b.harici_evrak_no)].append(b)
    for belgeler in sayac.values():
        if len(belgeler) > 1:
            tekrar.append(belgeler)
    # 3) Açık mutabakat farkları
    mutabakat = []
    for m in son_mutabakatlar():
        oz = mutabakat_ozeti(m)
        if oz["fark_kurus"] != 0 or oz["farkli_satirlar"]:
            mutabakat.append(oz)
    # 4) KDV'si bilinmeyen alış belgeleri (bilgi)
    kdv_bilinmeyen = Belge.objects.filter(iptal=False, tur__in=ALIS_TURLERI,
                                          kdv_modu="BILINMIYOR").count()
    return {"eksi_bakiye": eksi, "tekrar_evrak_no": tekrar, "mutabakat": mutabakat,
            "kdv_bilinmeyen": kdv_bilinmeyen,
            "adet": len(eksi) + len(tekrar) + len(mutabakat)}
