(function () {
  const G = window.CariGrafik;
  const el = document.getElementById('g-malzeme');
  if (!el) return;
  const veri = JSON.parse(document.getElementById('malzeme-veri').textContent);
  G.ciz(() => new Chart(el, {
    type: 'line',
    data: { labels: veri.etiketler, datasets: veri.seriler.map((s, i) => ({
      label: s.ad, data: s.veri, spanGaps: true, borderColor: G.renk('--k' + ((i % 8) + 1)), backgroundColor: G.renk('--k' + ((i % 8) + 1)),
      borderWidth: 2.5, pointRadius: 4, pointHoverRadius: 6, tension: 0 })) },
    options: { ...G.ortak, interaction: { mode: 'nearest', intersect: false },
      plugins: { tooltip: { ...G.ipucuStilKullan(), callbacks: { label: (c) => `${c.dataset.label}: ${G.tl.format(c.parsed.y)}` } },
        legend: { display: veri.seriler.length > 1, position: 'top', align: 'start', labels: { usePointStyle: true, boxWidth: 8, padding: 14 } } },
      scales: { y: { ...G.eksenTL(), beginAtZero: false }, x: { grid: { display: false } } } },
  }));
})();
