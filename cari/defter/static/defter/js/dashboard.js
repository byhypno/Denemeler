(function () {
  const veri = JSON.parse(document.getElementById('grafik-veri').textContent);
  const css = getComputedStyle(document.documentElement);
  const renk = (ad) => css.getPropertyValue(ad).trim();
  const tl = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 2 });
  const tam = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
  const lira = (kurus) => kurus === null ? null : kurus / 100;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = renk('--muted');
  Chart.defaults.borderColor = renk('--grid');
  Chart.defaults.animation = false;
  const eksenTL = { ticks: { callback: (v) => tam.format(v) + ' ₺', maxTicksLimit: 7, maxRotation: 0 },
    grid: { color: renk('--grid') } };
  const ipucu = { callbacks: { label: (c) => `${c.dataset.label || c.label}: ${tl.format(c.parsed.y ?? c.parsed.x)}` } };
  const ortak = { responsive: true, maintainAspectRatio: false };

  new Chart(document.getElementById('g-aylik'), {
    data: {
      labels: veri.aylar,
      datasets: [
        { type: 'bar', label: 'Alış', data: veri.alis.map(lira), backgroundColor: renk('--alis') },
        { type: 'bar', label: 'Ödeme', data: veri.odeme.map(lira), backgroundColor: renk('--odeme') },
        { type: 'bar', label: 'İade', data: veri.iade.map(lira), backgroundColor: renk('--iade') },
        { type: 'line', label: 'Ay sonu bakiye', data: veri.ay_sonu.map(lira), borderColor: renk('--bakiye'),
          backgroundColor: renk('--bakiye'), borderWidth: 2.5, pointRadius: 3, tension: 0, spanGaps: false },
      ],
    },
    options: { ...ortak, interaction: { mode: 'index', intersect: false },
      plugins: { tooltip: ipucu, legend: { position: 'top', labels: { usePointStyle: true } } },
      scales: { y: eksenTL, x: { grid: { display: false } } } },
  });

  new Chart(document.getElementById('g-yas'), {
    type: 'bar',
    data: { labels: veri.yas_etiket, datasets: [{ label: 'Açık borç', data: veri.yas_deger.map(lira),
      backgroundColor: renk('--yas'), borderRadius: 4 }] },
    options: { ...ortak, plugins: { legend: { display: false }, tooltip: ipucu },
      scales: { y: eksenTL, x: { grid: { display: false } } } },
  });

  function yatay(id, etiket, deger, ad) {
    const el = document.getElementById(id);
    if (!el) return;
    const kisalt = (k) => (k.length > 30 ? k.slice(0, 29) + '…' : k);
    new Chart(el, {
      type: 'bar',
      data: { labels: etiket.map(kisalt),
        datasets: [{ label: ad, data: deger.map(lira), backgroundColor: renk('--alis'), borderRadius: 4,
          maxBarThickness: 36 }] },
      options: { ...ortak, indexAxis: 'y',
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (c) => etiket[c[0].dataIndex],
            label: (c) => `${ad}: ${tl.format(c.parsed.x)}` } } },
        scales: { x: eksenTL, y: { grid: { display: false } } } },
    });
  }
  yatay('g-borclu', veri.borclu_etiket, veri.borclu_deger, 'Borç');
  yatay('g-kalem', veri.kalem_etiket, veri.kalem_deger, 'Alış tutarı');
})();
