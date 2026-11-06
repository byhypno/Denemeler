"""Mevcut Excel çalışma dosyasından (Egeser_Tedarikci_Cari_Takip.xlsx) içe aktarma.

Tutarlar önbellekteki (Excel'in hesapladığı) değerlerden okunur ve kuruşa çevrilir.
Hiçbir şey sessizce atlanmaz: sorunlar `uyarilar` / `hatalar` listesinde döner.
"""
import os
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal

import openpyxl
from django.db import transaction

from . import gunluk

from .models import Belge, BelgeKalem, Cari, EkstreMutabakat, EkstreSatiri

TUR_HARITASI = {
    "açılış / devir": Belge.Tur.ACILIS,
    "alış fişi": Belge.Tur.ALIS_FISI,
    "alış faturası": Belge.Tur.ALIS_FATURASI,
    "iade": Belge.Tur.IADE,
    "ödeme": Belge.Tur.ODEME,
    "düzeltme (+)": Belge.Tur.DUZELTME_ARTI,
    "düzeltme (-)": Belge.Tur.DUZELTME_EKSI,
}
ODEME_HARITASI = {
    "havale/eft": Belge.OdemeSekli.HAVALE, "nakit": Belge.OdemeSekli.NAKIT,
    "kredi kartı": Belge.OdemeSekli.KREDI_KARTI, "çek": Belge.OdemeSekli.CEK,
    "senet": Belge.OdemeSekli.SENET, "mahsup": Belge.OdemeSekli.MAHSUP,
}


def _norm(s) -> str:
    s = unicodedata.normalize("NFC", str(s)).strip()
    return s.replace("−", "-").replace("–", "-")


def _anahtar(s) -> str:
    return _norm(s).replace("I", "ı").replace("İ", "i").lower()


def kurus(deger) -> int:
    """Excel hücre değeri -> tamsayı kuruş (float artıklarını yuvarlayarak)."""
    return int((Decimal(str(deger)) * 100).quantize(Decimal(1)))


def _metin(deger) -> str:
    if deger is None:
        return ""
    if isinstance(deger, float) and deger.is_integer():
        deger = int(deger)
    return _norm(deger)


def _tarih(deger) -> date | None:
    if isinstance(deger, datetime):
        return deger.date()
    if isinstance(deger, date):
        return deger
    return None


def _sayfa(wb, ad):
    hedef = _anahtar(ad)
    for ws in wb.worksheets:
        if _anahtar(ws.title) == hedef:
            return ws
    raise ValueError(f"Excel'de '{ad}' sayfası yok. Mevcut: {[w.title for w in wb.worksheets]}")


def _baslik_satiri(ws, ilk_hucre: str) -> int:
    for i, satir in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
        if satir and satir[0] is not None and _anahtar(satir[0]) == _anahtar(ilk_hucre):
            return i
    raise ValueError(f"'{ws.title}' sayfasında '{ilk_hucre}' başlıklı satır bulunamadı.")


def excel_beklenen_bakiyeler(yol) -> dict:
    """Excel'in kendi hesapladığı güncel borç (Tedarikçiler sayfası) -> {ünvan: kuruş}."""
    wb = openpyxl.load_workbook(yol, data_only=True)
    ws = _sayfa(wb, "Tedarikçiler")
    b = _baslik_satiri(ws, "Tedarikçi Adı")
    sonuc = {}
    for satir in ws.iter_rows(min_row=b + 1, values_only=True):
        if satir[0] and satir[10] is not None:
            sonuc[_norm(satir[0])] = kurus(satir[10])
    return sonuc


def ice_aktar(yol, sifirla: bool = False) -> dict:
    """Excel'den içe aktarır. Binlerce kaydı tek tek günlüğe yazmak yerine tek bir özet kaydı yazılır."""
    ad = os.path.basename(str(yol))
    with gunluk.sessiz(f"Excel içe aktarma: {ad}") as g:
        sonuc = _ice_aktar(yol, sifirla)
        if sonuc["hatalar"]:
            g["metin"] = (f"Excel içe aktarma BAŞARISIZ, geri alındı: {ad} · {len(sonuc['hatalar'])} hata "
                          f"(sıfırla={sifirla}).")
        else:
            g["metin"] = (f"Excel içe aktarma: {ad} · cari {sonuc['cari']}, belge {sonuc['belge']}, "
                          f"kalem {sonuc['kalem']}, mutabakat satırı {sonuc['mutabakat_satiri']}; "
                          f"uyarı {len(sonuc['uyarilar'])} (sıfırla={sifirla}).")
    return sonuc


@transaction.atomic
def _ice_aktar(yol, sifirla: bool = False) -> dict:
    if Belge.objects.exists():
        if not sifirla:
            raise RuntimeError("Veritabanında zaten belge var. Üzerine yazmak için --sifirla kullanın.")
        EkstreMutabakat.objects.all().delete()
        BelgeKalem.objects.all().delete()
        Belge.objects.all().delete()
        Cari.objects.all().delete()

    wb = openpyxl.load_workbook(yol, data_only=True)
    uyarilar, hatalar = [], []
    cariler = {}

    # --- Tedarikçiler ---
    ws = _sayfa(wb, "Tedarikçiler")
    b = _baslik_satiri(ws, "Tedarikçi Adı")
    for s in ws.iter_rows(min_row=b + 1, values_only=True):
        if not s[0]:
            continue
        ad = _norm(s[0])
        vade = s[7]
        cariler[ad] = Cari.objects.create(
            unvan=ad, kisa_kod=_metin(s[1]), tedarikcideki_kodumuz=_metin(s[2]),
            vergi_bilgisi=_metin(s[3]), telefon=_metin(s[4]), eposta=_metin(s[5]),
            yetkili=_metin(s[6]), vade_gun=int(vade) if isinstance(vade, (int, float)) else None,
            not_metni=_metin(s[11]) if len(s) > 11 else "",
        )

    # --- Hareketler ---
    ws = _sayfa(wb, "Hareketler")
    b = _baslik_satiri(ws, "Tarih")
    belgeler = {}
    for no, s in enumerate(ws.iter_rows(min_row=b + 1, values_only=True), start=b + 1):
        tarih = _tarih(s[0])
        if tarih is None:
            continue
        tur = TUR_HARITASI.get(_anahtar(s[1] or ""))
        if tur is None:
            hatalar.append(f"Hareketler satır {no}: bilinmeyen evrak türü '{s[1]}'")
            continue
        ad = _norm(s[2] or "")
        if ad not in cariler:
            cariler[ad] = Cari.objects.create(unvan=ad)
            uyarilar.append(f"Hareketler satır {no}: '{ad}' Tedarikçiler sayfasında yoktu, cari olarak eklendi.")
        tutar = next((v for v in (s[9], s[10], s[7]) if v not in (None, "")), None)
        if tutar is None or kurus(tutar) <= 0:
            hatalar.append(f"Hareketler satır {no}: tutar yok/sıfır ({s[1]}, {s[3]})")
            continue
        etki_excel = _anahtar(s[8] or "")
        etki_beklenen = "artırır" if tur in Belge.ARTIRAN else "azaltır"
        if etki_excel and etki_excel != etki_beklenen:
            hatalar.append(f"Hareketler satır {no}: etki uyuşmuyor (Excel '{s[8]}', tür '{s[1]}')")
        belge = Belge(
            cari=cariler[ad], tur=tur, tarih=tarih, evrak_no=_metin(s[3]),
            harici_evrak_no=_metin(s[4]), aciklama=_metin(s[5]),
            odeme_sekli=ODEME_HARITASI.get(_anahtar(s[6] or ""), ""),
            tutar_kurus=kurus(tutar), kaynak_notu=_metin(s[13])[:250] if len(s) > 13 else "",
        )
        belge.save()
        if belge.evrak_no:
            belgeler[(ad, belge.evrak_no)] = belge

    # --- Fiş kalemleri ---
    ws = _sayfa(wb, "Fiş Kalemleri")
    b = _baslik_satiri(ws, "Fiş No")
    sira = {}
    kalem_sayisi = 0
    for no, s in enumerate(ws.iter_rows(min_row=b + 1, values_only=True), start=b + 1):
        if s[0] in (None, ""):
            continue
        fis, ad = _metin(s[0]), _norm(s[2] or "")
        belge = belgeler.get((ad, fis))
        if belge is None:
            uyarilar.append(f"Fiş Kalemleri satır {no}: '{fis}' numaralı fişin hareketi yok, kalem atlandı.")
            continue
        if s[8] is None:
            hatalar.append(f"Fiş Kalemleri satır {no}: kalem tutarı boş (fiş {fis})")
            continue
        sira[belge.pk] = sira.get(belge.pk, 0) + 1
        BelgeKalem.objects.create(
            belge=belge, sira=sira[belge.pk], stok_kodu=_metin(s[3]), aciklama=_metin(s[4])[:250],
            miktar=Decimal(str(s[5] if s[5] is not None else 1)), birim=_metin(s[6]),
            birim_fiyat=Decimal(str(s[7])) if s[7] is not None else None, tutar_kurus=kurus(s[8]),
        )
        kalem_sayisi += 1

    # --- Kalem toplamı ↔ belge tutarı kontrolü (bilgi amaçlı) ---
    from django.db.models import Sum
    kalem_farki = []
    for belge in belgeler.values():
        toplam = belge.kalemler.aggregate(t=Sum("tutar_kurus"))["t"]
        if toplam is not None and toplam != belge.tutar_kurus:
            kalem_farki.append((belge.evrak_no, belge.tutar_kurus, toplam))
    for evrak, tutar, toplam in kalem_farki:
        uyarilar.append(f"Fiş {evrak}: belge tutarı ile kalem toplamı farklı ({tutar} ≠ {toplam} kuruş)")

    # --- Ekstre mutabakatı (sayfa yoksa atlanır) ---
    mutabakat_satir = _mutabakat_aktar(wb, cariler, belgeler, uyarilar, hatalar)

    ozet = {
        "cari": len(cariler), "belge": Belge.objects.count(), "kalem": kalem_sayisi,
        "mutabakat_satiri": mutabakat_satir,
        "uyarilar": uyarilar, "hatalar": hatalar,
    }
    if hatalar:
        # Hata varsa HİÇBİR şey kaydedilmez (sayımlar rollback'ten önce alındı).
        transaction.set_rollback(True)
    return ozet


def _mutabakat_aktar(wb, cariler, belgeler, uyarilar, hatalar) -> int:
    try:
        ws = _sayfa(wb, "Ekstre Mutabakatı")
    except ValueError:
        return 0
    satirlar = list(ws.iter_rows(values_only=True))
    baslik = _norm(satirlar[0][0] or "") if satirlar else ""
    ad = _norm(baslik.split("—", 1)[1]) if "—" in baslik else ""
    cari = cariler.get(ad)
    if cari is None:
        uyarilar.append(f"Ekstre Mutabakatı: '{ad}' carisi bulunamadı, sayfa atlandı.")
        return 0
    tarih = None
    for s in satirlar[:4]:
        for hucre in s:
            m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(hucre or ""))
            if m:
                tarih = date(int(m[3]), int(m[2]), int(m[1]))
                break
        if tarih:
            break
    ekstre_bakiye = None
    for s in satirlar:
        if s[0] and _anahtar(s[0]).startswith("bakiye") and s[5] is not None:
            ekstre_bakiye = kurus(s[5])
    if tarih is None or ekstre_bakiye is None:
        hatalar.append("Ekstre Mutabakatı: ekstre tarihi veya ekstre bakiyesi bulunamadı.")
        return 0
    m = EkstreMutabakat.objects.create(cari=cari, ekstre_tarihi=tarih, ekstre_bakiye_kurus=ekstre_bakiye)
    baslik_i = _baslik_satiri(ws, "Fiş No")
    sayi = 0
    for no, s in enumerate(ws.iter_rows(min_row=baslik_i + 1, values_only=True), start=baslik_i + 1):
        if s[0] in (None, ""):
            continue
        if _anahtar(s[0]) == "özet":
            break
        fis = _metin(s[0])
        belge = belgeler.get((ad, fis))
        ekstre_tutar = kurus(s[5]) if s[5] is not None else None
        if belge is None:
            uyarilar.append(f"Ekstre Mutabakatı satır {no}: '{fis}' numaralı bizim kaydımız yok.")
        elif s[3] is not None and kurus(s[3]) != belge.tutar_kurus:
            uyarilar.append(f"Ekstre Mutabakatı satır {no}: 'Bizim kayıt' tutarı belge tutarından farklı.")
        aciklama = _metin(s[7])
        if aciklama.startswith("✓"):
            aciklama = ""
        sayi += 1
        satir = EkstreSatiri.objects.create(
            mutabakat=m, sira=sayi, belge=belge, tarih=_tarih(s[1]), tur_metni=_metin(s[2]),
            ekstre_evrak_no=_metin(s[4]), ekstre_tutar_kurus=ekstre_tutar, aciklama=aciklama[:300])
        if s[6] is not None and satir.fark_kurus != kurus(s[6]):
            uyarilar.append(f"Ekstre Mutabakatı satır {no}: hesaplanan fark Excel'deki farktan farklı.")
    return sayi
