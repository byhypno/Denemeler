(function () {
  const G = window.CariGrafik;
  const veri = JSON.parse(document.getElementById('grafik-veri').textContent);

  new Chart(document.getElementById('g-aylik'), {
    data: {
      labels: veri.aylar,
      datasets: [
        { type: 'bar', label: 'Alış', data: veri.alis.map(G.lira), backgroundColor: G.renk('--alis') },
        { type: 'bar', label: 'Ödeme', data: veri.odeme.map(G.lira), backgroundColor: G.renk('--odeme') },
        { type: 'bar', label: 'İade', data: veri.iade.map(G.lira), backgroundColor: G.renk('--iade') },
        { type: 'line', label: 'Ay sonu bakiye', data: veri.ay_sonu.map(G.lira), borderColor: G.renk('--bakiye'),
          backgroundColor: G.renk('--bakiye'), borderWidth: 2.5, pointRadius: 3, tension: 0, spanGaps: false },
      ],
    },
    options: { ...G.ortak, interaction: { mode: 'index', intersect: false },
      plugins: { tooltip: G.ipucu, legend: { position: 'top', labels: { usePointStyle: true } } },
      scales: { y: G.eksenTL, x: { grid: { display: false } } } },
  });

  new Chart(document.getElementById('g-yas'), {
    type: 'bar',
    data: { labels: veri.yas_etiket, datasets: [{ label: 'Açık borç', data: veri.yas_deger.map(G.lira),
      backgroundColor: G.renk('--yas'), borderRadius: 4 }] },
    options: { ...G.ortak, plugins: { legend: { display: false }, tooltip: G.ipucu },
      scales: { y: G.eksenTL, x: { grid: { display: false } } } },
  });

  G.yatay('g-borclu', veri.borclu_etiket, veri.borclu_deger, 'Borç');
  G.yatay('g-kalem', veri.kalem_etiket, veri.kalem_deger, 'Alış tutarı');
})();
