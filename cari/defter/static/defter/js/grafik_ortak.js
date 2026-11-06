// Panolar arasında paylaşılan grafik yardımcıları (Chart.js yerel kopyası gerekir).
window.CariGrafik = (function () {
  const css = getComputedStyle(document.documentElement);
  const renk = (ad) => css.getPropertyValue(ad).trim();
  const tl = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 2 });
  const tam = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
  // Tutarlar veritabanında kuruştur; grafik yalnızca GÖSTERİM için liraya çevirir.
  const lira = (kurus) => (kurus === null ? null : kurus / 100);
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = renk('--muted');
  Chart.defaults.borderColor = renk('--grid');
  Chart.defaults.animation = false;
  const eksenTL = { ticks: { callback: (v) => tam.format(v) + ' ₺', maxTicksLimit: 7, maxRotation: 0 },
    grid: { color: renk('--grid') } };
  const ipucu = { callbacks: { label: (c) => `${c.dataset.label || c.label}: ${tl.format(c.parsed.y ?? c.parsed.x)}` } };
  const ortak = { responsive: true, maintainAspectRatio: false };

  function yatay(id, etiket, deger, ad, renkAdi) {
    const el = document.getElementById(id);
    if (!el) return;
    const kisalt = (k) => (k.length > 30 ? k.slice(0, 29) + '…' : k);
    new Chart(el, {
      type: 'bar',
      data: { labels: etiket.map(kisalt),
        datasets: [{ label: ad, data: deger.map(lira), backgroundColor: renk(renkAdi || '--alis'),
          borderRadius: 4, maxBarThickness: 36 }] },
      options: { ...ortak, indexAxis: 'y',
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (c) => etiket[c[0].dataIndex],
            label: (c) => `${ad}: ${tl.format(c.parsed.x)}` } } },
        scales: { x: eksenTL, y: { grid: { display: false } } } },
    });
  }
  return { renk, tl, tam, lira, eksenTL, ipucu, ortak, yatay };
})();
