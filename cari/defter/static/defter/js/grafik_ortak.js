// Panolar arasında paylaşılan grafik yardımcıları (Chart.js yerel kopyası gerekir).
// Renkler CSS token'larından okunur (--g-*, --metin-2...) ve tema değişince grafikler yeniden çizilir.
window.CariGrafik = (function () {
  const tl = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 2 });
  const tam = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
  // Tutarlar veritabanında kuruştur; grafik yalnızca GÖSTERİM için liraya çevirir.
  const lira = (kurus) => (kurus === null ? null : kurus / 100);
  const renk = (ad) => getComputedStyle(document.documentElement).getPropertyValue(ad).trim();

  function varsayilanlar() {
    Chart.defaults.font.family = renk('--font') || 'system-ui, sans-serif';
    Chart.defaults.font.size = 12.5;
    Chart.defaults.color = renk('--metin-2');
    Chart.defaults.borderColor = renk('--g-izgara');
    Chart.defaults.animation = false;
  }
  // '#RRGGBB' token + saydamlık -> rgba(); alan dolgusu için
  function saydam(ad, a) {
    const h = renk(ad).replace('#', '');
    if (h.length !== 6) return renk(ad);
    const n = parseInt(h, 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }
  // çizginin altına yukarıdan aşağı sönen dolgu (gradient grafik alanına göre kurulur)
  function alanDolgu(ad) {
    return (ctx) => {
      const { chart } = ctx, a = chart.chartArea;
      if (!a) return saydam(ad, 0.12);
      const g = chart.ctx.createLinearGradient(0, a.top, 0, a.bottom);
      g.addColorStop(0, saydam(ad, 0.22)); g.addColorStop(1, saydam(ad, 0));
      return g;
    };
  }
  const eksenTL = () => ({ ticks: { callback: (v) => tam.format(v) + ' ₺', maxTicksLimit: 7, maxRotation: 0 },
    grid: { color: renk('--g-izgara') }, border: { display: false } });
  const ipucuStil = () => ({ backgroundColor: renk('--ipucu-bg'), titleColor: renk('--ipucu-metin'), bodyColor: renk('--ipucu-metin'),
    padding: 12, cornerRadius: 10, boxPadding: 6, usePointStyle: true, titleFont: { weight: '600' } });
  // Tema değişince yeniden okunsun diye fonksiyondur: plugins: { tooltip: G.ipucu() }
  const ipucu = () => ({ ...ipucuStil(), callbacks: { label: (c) => `${c.dataset.label || c.label}: ${tl.format(c.parsed.y ?? c.parsed.x)}` } });
  const ortak = { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 8 } } };

  function yatay(id, etiket, deger, ad, renkAdi) {
    const el = document.getElementById(id);
    if (!el) return null;
    const kisalt = (k) => (k.length > 24 ? k.slice(0, 23) + '…' : k);
    return new Chart(el, {
      type: 'bar',
      data: { labels: etiket.map(kisalt),
        datasets: [{ label: ad, data: deger.map(lira), backgroundColor: renk(renkAdi || '--g-odeme'),
          borderRadius: 6, borderSkipped: false, maxBarThickness: 22 }] },
      options: { ...ortak, indexAxis: 'y',
        plugins: { legend: { display: false },
          tooltip: { ...ipucuStil(), callbacks: { title: (c) => etiket[c[0].dataIndex], label: (c) => `${ad}: ${tl.format(c.parsed.x)}` } } },
        scales: { x: eksenTL(), y: { grid: { display: false }, border: { display: false } } } },
    });
  }

  // ciz(() => [grafik, ...]): oluşturucu ilk çizimde ve her tema değişiminde çalışır.
  const oluşturucular = [], ornekler = [];
  function yenidenCiz() {
    ornekler.splice(0).forEach((c) => c.destroy());
    varsayilanlar();
    oluşturucular.forEach((o) => [].concat(o() || []).forEach((c) => c && ornekler.push(c)));
  }
  function ciz(olusturucu) { oluşturucular.push(olusturucu); yenidenCiz(); }
  document.addEventListener('tema-degisti', yenidenCiz);
  // Web yazı tipi yüklenince yeniden çiz: grafik, yazı tipi gelmeden ölçerse etiketler kesilir.
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (oluşturucular.length) yenidenCiz(); });

  return { renk, saydam, alanDolgu, ipucuStilKullan: ipucuStil, tl, tam, lira, eksenTL, ipucu, ortak, yatay, ciz };
})();
