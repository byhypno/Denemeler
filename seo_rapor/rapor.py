#!/usr/bin/env python3
"""Egeser siteleri için günlük Google raporu.

Topladığı veriler:
  * Google Search Console (ücretsiz, resmi):
      - Web aramada tıklama / gösterim / ortalama sıra (gün ve 7 gün)
      - Her arama kelimesinin 7 günlük ortalama sırası ve önceki 7 güne göre değişimi
      - Google Görseller'de gösterim / tıklama / ortalama sıra,
        görsel aramada gösterim alan sayfa sayısı ve görsel arama kelimeleri
  * Sitemap: sitede kaç sayfa ve kaç görsel olduğu
  * (İsteğe bağlı) SerpAPI: takip kelimelerinde Google'daki anlık sıra ve
    Google Görseller'de "site:" aramasında çıkan görsel sayısı

Çıktılar:
  seo_rapor/veri/<tarih>.json        ham veri (geçmiş karşılaştırma için)
  seo_rapor/raporlar/<tarih>.html    okunur rapor
  seo_rapor/raporlar/son.md          en son raporun özeti
  (SMTP ayarlıysa) e-posta

Ortam değişkenleri:
  GSC_SERVICE_ACCOUNT_JSON   service account JSON içeriği (veya GOOGLE_APPLICATION_CREDENTIALS dosya yolu)
  SERPAPI_KEY                isteğe bağlı
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, RAPOR_ALICI   isteğe bağlı (e-posta)

Kullanım:
  python seo_rapor/rapor.py            gerçek veriyle
  python seo_rapor/rapor.py --ornek    kimlik bilgisi olmadan, uydurma GSC verisiyle deneme
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import random
import smtplib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from pathlib import Path

KOK = Path(__file__).resolve().parent
VERI = KOK / "veri"
RAPORLAR = KOK / "raporlar"
UA = "Mozilla/5.0 (compatible; seo-rapor/1.0)"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- sitemap

def _getir(url: str, zaman_asimi: int = 60) -> bytes:
    istek = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        return yanit.read()


def sitemap_say(sitemaps: list[str]) -> dict:
    """Sitemap(ler)deki benzersiz sayfa ve görsel adreslerini sayar."""
    sayfalar, gorseller, hatalar = set(), set(), []
    ziyaret, kuyruk = set(), list(sitemaps)
    while kuyruk:
        url = kuyruk.pop(0)
        if url in ziyaret or len(ziyaret) > 200:
            continue
        ziyaret.add(url)
        try:
            kok = ET.fromstring(_getir(url))
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{url}: {e}")
            continue
        for el in kok.iter():
            ad = el.tag.rsplit("}", 1)[-1]
            ust = el.tag.split("}")[0]
            metin = (el.text or "").strip()
            if not metin or ad != "loc":
                continue
            if "sitemap-image" in ust:
                gorseller.add(metin)
            elif kok.tag.endswith("sitemapindex"):
                kuyruk.append(metin)
            else:
                sayfalar.add(metin)
    return {"sayfa": len(sayfalar), "gorsel": len(gorseller), "hatalar": hatalar}


# ---------------------------------------------------------------- Search Console

def gsc_servis():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    kapsam = ["https://www.googleapis.com/auth/webmasters.readonly"]
    icerik = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
    if icerik:
        kimlik = service_account.Credentials.from_service_account_info(json.loads(icerik), scopes=kapsam)
    elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        kimlik = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=kapsam)
    else:
        raise SystemExit("GSC_SERVICE_ACCOUNT_JSON tanımlı değil (deneme için --ornek kullanın).")
    return build("searchconsole", "v1", credentials=kimlik, cache_discovery=False)


def gsc_mulk_bul(servis, site: dict, mulkler: list[str]) -> str | None:
    alan = site["alan_adi"]
    adaylar = [f"sc-domain:{alan}", site["adres"], f"https://{alan}/",
               f"https://www.{alan}/", f"http://www.{alan}/", f"http://{alan}/"]
    for a in adaylar:
        if a in mulkler:
            return a
    return None


def gsc_sorgu(servis, mulk, bas, bit, tip="web", boyutlar=None, satir=1000):
    govde = {"startDate": str(bas), "endDate": str(bit), "type": tip,
             "rowLimit": satir, "dataState": "final"}
    if boyutlar:
        govde["dimensions"] = boyutlar
    yanit = servis.searchanalytics().query(siteUrl=mulk, body=govde).execute()
    return yanit.get("rows", [])


def _ozet(satirlar):
    if not satirlar:
        return {"tiklama": 0, "gosterim": 0, "ctr": 0.0, "sira": None}
    r = satirlar[0]
    return {"tiklama": r.get("clicks", 0), "gosterim": r.get("impressions", 0),
            "ctr": r.get("ctr", 0.0), "sira": round(r["position"], 1) if r.get("impressions") else None}


def _sorgu_tablosu(satirlar):
    return {r["keys"][0]: {"tiklama": r["clicks"], "gosterim": r["impressions"],
                           "sira": round(r["position"], 1)} for r in satirlar}


def gsc_site_topla(servis, mulk) -> dict:
    # Kesinleşmiş verinin olduğu en son günü bul (genelde 2-3 gün önce).
    bugun = dt.date.today()
    gunler = gsc_sorgu(servis, mulk, bugun - dt.timedelta(days=14), bugun, boyutlar=["date"])
    son = max((dt.date.fromisoformat(r["keys"][0]) for r in gunler), default=bugun - dt.timedelta(days=3))
    onceki_gun = son - dt.timedelta(days=1)
    h_bas, h_bit = son - dt.timedelta(days=6), son            # son 7 gün
    o_bas, o_bit = son - dt.timedelta(days=13), son - dt.timedelta(days=7)  # önceki 7 gün

    v = {"mulk": mulk, "veri_tarihi": str(son), "hafta": [str(h_bas), str(h_bit)]}
    for tip in ("web", "image"):
        v[tip] = {
            "gun": _ozet(gsc_sorgu(servis, mulk, son, son, tip)),
            "onceki_gun": _ozet(gsc_sorgu(servis, mulk, onceki_gun, onceki_gun, tip)),
            "hafta": _ozet(gsc_sorgu(servis, mulk, h_bas, h_bit, tip)),
            "onceki_hafta": _ozet(gsc_sorgu(servis, mulk, o_bas, o_bit, tip)),
            "sorgular": _sorgu_tablosu(gsc_sorgu(servis, mulk, h_bas, h_bit, tip, ["query"])),
            "sorgular_onceki": _sorgu_tablosu(gsc_sorgu(servis, mulk, o_bas, o_bit, tip, ["query"])),
            "sayfa_sayisi": len(gsc_sorgu(servis, mulk, h_bas, h_bit, tip, ["page"], 25000)),
        }
    return v


def ornek_site_veri(site: dict, kelimeler: list[str]) -> dict:
    """Kimlik bilgisi olmadan rapor biçimini denemek için uydurma veri."""
    rnd = random.Random(site["alan_adi"])
    son = dt.date.today() - dt.timedelta(days=3)

    def ozet(g):
        return {"tiklama": g // 20, "gosterim": g, "ctr": 0.05, "sira": round(rnd.uniform(5, 25), 1)}

    def sorgular():
        return {k: {"tiklama": rnd.randint(0, 30), "gosterim": rnd.randint(20, 900),
                    "sira": round(rnd.uniform(1, 40), 1)} for k in kelimeler + [f"{site['ad'].lower()} {i}" for i in range(15)]}
    v = {"mulk": f"sc-domain:{site['alan_adi']}", "veri_tarihi": str(son),
         "hafta": [str(son - dt.timedelta(days=6)), str(son)], "ornek": True}
    for tip, carpan in (("web", 1), ("image", 3)):
        v[tip] = {"gun": ozet(120 * carpan), "onceki_gun": ozet(110 * carpan),
                  "hafta": ozet(800 * carpan), "onceki_hafta": ozet(760 * carpan),
                  "sorgular": sorgular(), "sorgular_onceki": sorgular(),
                  "sayfa_sayisi": rnd.randint(10, 60)}
    return v


# ---------------------------------------------------------------- SerpAPI (isteğe bağlı)

def _serpapi(params: dict) -> dict:
    params = {**params, "api_key": os.environ["SERPAPI_KEY"]}
    return json.loads(_getir("https://serpapi.com/search.json?" + urllib.parse.urlencode(params), 90))


def _alan_eslesir(link: str, alan: str) -> bool:
    host = urllib.parse.urlparse(link).netloc.lower()
    return host == alan or host.endswith("." + alan)


def serpapi_siralama(kelimeler, alanlar, ayar) -> dict:
    """Her kelime için her alan adının organik sonuçlardaki ilk sırası (bulunamazsa None)."""
    sonuc = {}
    for k in kelimeler:
        bulunan = {a: None for a in alanlar}
        for sayfa in range(ayar.get("en_fazla_sayfa", 3)):
            try:
                y = _serpapi({"engine": "google", "q": k, "google_domain": ayar["google_domain"],
                              "gl": ayar["gl"], "hl": ayar["hl"], "location": ayar.get("konum", ""),
                              "start": sayfa * 10})
            except Exception as e:  # noqa: BLE001
                log(f"SerpAPI hata ({k}): {e}")
                break
            sonuclar = y.get("organic_results", [])
            for r in sonuclar:
                for a in alanlar:
                    if bulunan[a] is None and _alan_eslesir(r.get("link", ""), a):
                        bulunan[a] = r.get("position")
            if all(bulunan.values()) or not sonuclar:
                break
        sonuc[k] = bulunan
    return sonuc


def serpapi_gorsel_sayisi(alan, ayar) -> int | None:
    """Google Görseller'de 'site:alan' aramasında listelenen görsel sayısı (yaklaşık, en fazla ~100/sayfa)."""
    toplam = 0
    try:
        for sayfa in range(3):
            y = _serpapi({"engine": "google_images", "q": f"site:{alan}", "google_domain": ayar["google_domain"],
                          "gl": ayar["gl"], "hl": ayar["hl"], "ijn": sayfa})
            n = len(y.get("images_results", []))
            toplam += n
            if n < 90:
                break
    except Exception as e:  # noqa: BLE001
        log(f"SerpAPI görsel hata ({alan}): {e}")
        return None
    return toplam


# ---------------------------------------------------------------- yardımcılar

def _fark(simdi, once, ters=False, ondalik=0):
    if simdi is None or once is None:
        return ""
    d = round(simdi - once, ondalik)
    if d == 0:
        return "="
    iyi = d < 0 if ters else d > 0
    ok = "▲" if iyi else "▼"
    return f"{ok} {abs(d):g}"


def _sira(s):
    return "—" if s is None else f"{s:g}"


def onceki_raporu_bul(bugun: str) -> dict | None:
    if not VERI.exists():
        return None
    dosyalar = sorted(p for p in VERI.glob("*.json") if p.stem < bugun)
    return json.loads(dosyalar[-1].read_text("utf-8")) if dosyalar else None


# ---------------------------------------------------------------- rapor üretimi

def site_bolumu(site, sv, ayar, onceki_site) -> tuple[str, list[str]]:
    """Bir site için (HTML, md satırları) döndürür."""
    e = html.escape
    g = sv.get("gsc")
    sm = sv["sitemap"]
    md = [f"## {site['ad']} ({site['alan_adi']})", ""]
    h = [f"<h2>{e(site['ad'])} <small>{e(site['alan_adi'])}</small></h2>"]

    if not g:
        msg = sv.get("gsc_hata", "Search Console verisi alınamadı.")
        h.append(f"<p class='uyari'>{e(msg)}</p>")
        md.append(f"> {msg}")
    else:
        ornek = " (ÖRNEK VERİ)" if g.get("ornek") else ""
        h.append(f"<p class='not'>Search Console verisi: {e(g['veri_tarihi'])} günü · "
                 f"7 gün: {e(g['hafta'][0])} – {e(g['hafta'][1])}{ornek}</p>")
        md.append(f"Veri günü: {g['veri_tarihi']}{ornek}")
        md.append("")

        # Özet tablosu
        h.append("<table><tr><th></th><th>Tıklama</th><th>Gösterim</th><th>Ort. sıra</th>"
                 "<th>Tıklama (7g)</th><th>Gösterim (7g)</th><th>Ort. sıra (7g)</th></tr>")
        md += ["| | Tıklama | Gösterim | Ort. sıra | Gösterim (7g) | Ort. sıra (7g) |",
               "|---|---|---|---|---|---|"]
        for tip, ad in (("web", "Google Arama"), ("image", "Google Görseller")):
            t = g[tip]
            gn, og, hf, oh = t["gun"], t["onceki_gun"], t["hafta"], t["onceki_hafta"]
            h.append(
                f"<tr><th>{ad}</th>"
                f"<td>{gn['tiklama']:g} <i>{_fark(gn['tiklama'], og['tiklama'])}</i></td>"
                f"<td>{gn['gosterim']:g} <i>{_fark(gn['gosterim'], og['gosterim'])}</i></td>"
                f"<td>{_sira(gn['sira'])} <i>{_fark(gn['sira'], og['sira'], True, 1)}</i></td>"
                f"<td>{hf['tiklama']:g} <i>{_fark(hf['tiklama'], oh['tiklama'])}</i></td>"
                f"<td>{hf['gosterim']:g} <i>{_fark(hf['gosterim'], oh['gosterim'])}</i></td>"
                f"<td>{_sira(hf['sira'])} <i>{_fark(hf['sira'], oh['sira'], True, 1)}</i></td></tr>")
            md.append(f"| {ad} | {gn['tiklama']:g} | {gn['gosterim']:g} {_fark(gn['gosterim'], og['gosterim'])} | "
                      f"{_sira(gn['sira'])} | {hf['gosterim']:g} {_fark(hf['gosterim'], oh['gosterim'])} | "
                      f"{_sira(hf['sira'])} {_fark(hf['sira'], oh['sira'], True, 1)} |")
        h.append("</table><p class='not'>▲ iyileşme, ▼ kötüleşme (önceki güne / önceki 7 güne göre). "
                 "Sırada küçük sayı daha iyidir.</p>")
        md.append("")

    # Görsel durumu
    img = g["image"] if g else None
    serp_g = sv.get("serp_gorsel")
    satirlar = [("Sitemap'teki sayfa sayısı", sm["sayfa"]),
                ("Sitemap'teki görsel sayısı", sm["gorsel"])]
    if img:
        satirlar.append(("Google Görseller'de gösterim alan sayfa (7 gün)", img["sayfa_sayisi"]))
        satirlar.append(("Google Görseller'de gösterim (7 gün)", f"{img['hafta']['gosterim']:g}"))
        satirlar.append(("Google Görseller'de tıklama (7 gün)", f"{img['hafta']['tiklama']:g}"))
    if serp_g is not None:
        once = (onceki_site or {}).get("serp_gorsel")
        satirlar.append(("Google Görseller 'site:' aramasında listelenen görsel", f"{serp_g} {_fark(serp_g, once)}"))
    h.append("<h3>Görseller</h3><table>" + "".join(f"<tr><th>{e(a)}</th><td>{d}</td></tr>" for a, d in satirlar) + "</table>")
    md += ["**Görseller**", ""] + [f"- {a}: {d}" for a, d in satirlar] + [""]
    if sm["hatalar"]:
        h.append("<p class='uyari'>Sitemap okunamadı: " + e("; ".join(sm["hatalar"])) + "</p>")

    if not g:
        return "\n".join(h), md

    r = ayar["rapor"]
    # Takip kelimeleri (GSC + SerpAPI)
    serp = sv.get("serp_sira") or {}
    onceki_serp = (onceki_site or {}).get("serp_sira") or {}
    h.append("<h3>Takip edilen kelimeler</h3><table><tr><th>Kelime</th><th>Search Console ort. sıra (7g)</th>"
             "<th>Değişim</th><th>Gösterim (7g)</th>" + ("<th>Google anlık sıra</th><th>Dün</th>" if serp else "") + "</tr>")
    md += ["**Takip edilen kelimeler**", "", "| Kelime | GSC ort. sıra (7g) | Değişim | Gösterim |"
           + (" Anlık sıra |" if serp else ""), "|---|---|---|---|" + ("---|" if serp else "")]
    for k in ayar["takip_kelimeleri"]:
        s = g["web"]["sorgular"].get(k)
        o = g["web"]["sorgular_onceki"].get(k)
        sira = s["sira"] if s else None
        degisim = _fark(sira, o["sira"] if o else None, True, 1)
        gos = s["gosterim"] if s else 0
        ek_h, ek_md = "", ""
        if serp:
            anlik = serp.get(k, {}).get(site["alan_adi"])
            dun = onceki_serp.get(k, {}).get(site["alan_adi"])
            ek_h = f"<td>{_sira(anlik) if anlik else '30+ / yok'}</td><td>{_sira(dun) if dun else '—'}</td>"
            ek_md = f" {_sira(anlik) if anlik else '30+'} |"
        h.append(f"<tr><td>{e(k)}</td><td>{_sira(sira)}</td><td>{degisim}</td><td>{gos:g}</td>{ek_h}</tr>")
        md.append(f"| {k} | {_sira(sira)} | {degisim} | {gos:g} |{ek_md}")
    h.append("</table>")
    md.append("")

    # En çok gösterim alan sorgular
    for tip, baslik in (("web", "En çok gösterim alan aramalar"), ("image", "Google Görseller'de en çok gösterim alan aramalar")):
        t = g[tip]
        sirali = sorted(t["sorgular"].items(), key=lambda x: -x[1]["gosterim"])[: r["en_iyi_sorgu_sayisi"]]
        h.append(f"<h3>{baslik} (7 gün)</h3>")
        if not sirali:
            h.append("<p class='not'>Veri yok.</p>")
            continue
        h.append("<table><tr><th>Arama</th><th>Ort. sıra</th><th>Değişim</th><th>Gösterim</th><th>Tıklama</th></tr>")
        md += [f"**{baslik}**", "", "| Arama | Sıra | Değişim | Gösterim | Tıklama |", "|---|---|---|---|---|"]
        for k, s in sirali:
            o = t["sorgular_onceki"].get(k)
            d = _fark(s["sira"], o["sira"] if o else None, True, 1) or "yeni"
            h.append(f"<tr><td>{e(k)}</td><td>{_sira(s['sira'])}</td><td>{d}</td><td>{s['gosterim']:g}</td><td>{s['tiklama']:g}</td></tr>")
            md.append(f"| {k} | {_sira(s['sira'])} | {d} | {s['gosterim']:g} | {s['tiklama']:g} |")
        h.append("</table>")
        md.append("")

    # En büyük yükselen / düşenler (yeterli gösterimi olanlar)
    ortak = []
    for k, s in g["web"]["sorgular"].items():
        o = g["web"]["sorgular_onceki"].get(k)
        if o and s["gosterim"] >= 10:
            ortak.append((round(o["sira"] - s["sira"], 1), k, s["sira"], o["sira"]))
    ortak.sort()
    yukselen = [x for x in reversed(ortak) if x[0] > 0][: r["hareket_sayisi"]]
    dusen = [x for x in ortak if x[0] < 0][: r["hareket_sayisi"]]
    for baslik, liste in (("En çok yükselen aramalar", yukselen), ("En çok düşen aramalar", dusen)):
        if not liste:
            continue
        h.append(f"<h3>{baslik}</h3><table><tr><th>Arama</th><th>Önceki 7g</th><th>Son 7g</th><th>Fark</th></tr>")
        h += [f"<tr><td>{e(k)}</td><td>{o:g}</td><td>{s:g}</td><td>{'▲' if f > 0 else '▼'} {abs(f):g}</td></tr>"
              for f, k, s, o in liste]
        h.append("</table>")
        md += [f"**{baslik}**: " + ", ".join(f"{k} ({o:g}→{s:g})" for f, k, s, o in liste), ""]
    return "\n".join(h), md


CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2933;max-width:900px;margin:0 auto;padding:16px;background:#fff}
h1{font-size:22px;margin:0 0 4px}h2{font-size:19px;margin:28px 0 6px;border-bottom:2px solid #e4e7eb;padding-bottom:4px}
h2 small{font-weight:400;color:#7b8794;font-size:14px}h3{font-size:15px;margin:18px 0 6px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:6px}
th,td{border:1px solid #e4e7eb;padding:5px 8px;text-align:left}th{background:#f5f7fa;font-weight:600}
td i{font-style:normal;color:#7b8794;font-size:12px;margin-left:4px}
.not{color:#7b8794;font-size:12px;margin:4px 0}.uyari{background:#fff4e5;border:1px solid #f0b429;padding:8px;font-size:13px}
"""


def rapor_olustur(tarih, veri, ayar, onceki) -> tuple[str, str]:
    govde, md = [], [f"# Günlük Google raporu — {tarih}", ""]
    for site in ayar["siteler"]:
        sv = veri["siteler"][site["alan_adi"]]
        onceki_site = (onceki or {}).get("siteler", {}).get(site["alan_adi"])
        h, m = site_bolumu(site, sv, ayar, onceki_site)
        govde.append(h)
        md += m
    aciklama = ("<p class='not'>Search Console verisi Google tarafından 2-3 gün gecikmeli kesinleşir. "
                "'Ort. sıra' o aramada sitenizin göründüğü ortalama konumdur. "
                "Google, dizindeki görsellerin kesin sayısını vermez; 'gösterim alan sayfa' sayısı, "
                "görselleri Google Görseller'de en az bir kez gösterilen sayfaları sayar.</p>")
    sayfa = (f"<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Google raporu {tarih}</title><style>{CSS}</style></head><body>"
             f"<h1>Günlük Google raporu</h1><p class='not'>{tarih}</p>"
             + "\n".join(govde) + aciklama + "</body></html>")
    return sayfa, "\n".join(md) + "\n"


def eposta_gonder(konu, html_icerik, md_icerik):
    gerekli = ["SMTP_HOST", "SMTP_USER", "SMTP_PASS", "RAPOR_ALICI"]
    if not all(os.environ.get(k) for k in gerekli):
        log("E-posta ayarı yok, gönderilmedi.")
        return
    mesaj = EmailMessage()
    mesaj["Subject"] = konu
    mesaj["From"] = os.environ.get("SMTP_FROM", os.environ["SMTP_USER"])
    mesaj["To"] = os.environ["RAPOR_ALICI"]
    mesaj.set_content(md_icerik)
    mesaj.add_alternative(html_icerik, subtype="html")
    port = int(os.environ.get("SMTP_PORT", "465"))
    if port == 465:
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=60) as s:
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(mesaj)
    else:
        with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=60) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(mesaj)
    log(f"E-posta gönderildi: {os.environ['RAPOR_ALICI']}")


# ---------------------------------------------------------------- ana akış

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ornek", action="store_true", help="Search Console yerine uydurma veri kullan (deneme)")
    p.add_argument("--eposta-yok", action="store_true", help="E-posta gönderme")
    p.add_argument("--kaydetme", action="store_true", help="veri/ ve raporlar/ klasörüne yazma, raporu ekrana bas")
    a = p.parse_args()

    ayar = json.loads((KOK / "ayarlar.json").read_text("utf-8"))
    tarih = dt.date.today().isoformat()
    onceki = onceki_raporu_bul(tarih)
    veri = {"tarih": tarih, "siteler": {}}

    servis, mulkler = None, []
    if not a.ornek:
        servis = gsc_servis()
        mulkler = [s["siteUrl"] for s in servis.sites().list().execute().get("siteEntry", [])]
        log("Erişilebilen Search Console mülkleri:", mulkler or "YOK")

    serp_ayar = ayar["serpapi"]
    serp_var = bool(os.environ.get("SERPAPI_KEY")) and not a.ornek
    serp_sira = (serpapi_siralama(ayar["takip_kelimeleri"], [s["alan_adi"] for s in ayar["siteler"]], serp_ayar)
                 if serp_var else {})

    for site in ayar["siteler"]:
        log(f"— {site['ad']}")
        sv = {"sitemap": sitemap_say(site["sitemaps"])}
        if a.ornek:
            sv["gsc"] = ornek_site_veri(site, ayar["takip_kelimeleri"])
        else:
            mulk = gsc_mulk_bul(servis, site, mulkler)
            if not mulk:
                sv["gsc"] = None
                sv["gsc_hata"] = (f"Search Console'da {site['alan_adi']} mülküne erişim yok. Service account e-postasını "
                                  "bu mülke 'Kullanıcı' olarak ekleyin.")
            else:
                try:
                    sv["gsc"] = gsc_site_topla(servis, mulk)
                except Exception as e:  # noqa: BLE001
                    sv["gsc"], sv["gsc_hata"] = None, f"Search Console hatası: {e}"
        if serp_var:
            sv["serp_sira"] = {k: {site["alan_adi"]: v.get(site["alan_adi"])} for k, v in serp_sira.items()}
            if serp_ayar.get("gorsel_sayimi"):
                sv["serp_gorsel"] = serpapi_gorsel_sayisi(site["alan_adi"], serp_ayar)
        veri["siteler"][site["alan_adi"]] = sv

    sayfa, md = rapor_olustur(tarih, veri, ayar, onceki)
    if a.kaydetme:
        print(md)
    else:
        VERI.mkdir(exist_ok=True)
        RAPORLAR.mkdir(exist_ok=True)
        if not a.ornek:
            (VERI / f"{tarih}.json").write_text(json.dumps(veri, ensure_ascii=False, indent=1), "utf-8")
        ad = f"{tarih}{'-ornek' if a.ornek else ''}"
        (RAPORLAR / f"{ad}.html").write_text(sayfa, "utf-8")
        (RAPORLAR / ("ornek.md" if a.ornek else "son.md")).write_text(md, "utf-8")
        log(f"Rapor yazıldı: {RAPORLAR / (ad + '.html')}")
    if not a.eposta_yok and not a.ornek:
        eposta_gonder(f"Google raporu {tarih} — Egeser", sayfa, md)


if __name__ == "__main__":
    main()
