(function () {
  const G = window.CariGrafik;
  const veri = JSON.parse(document.getElementById('gider-veri').textContent);
  const el = document.getElementById('g-gider');
  if (!el) return;
  G.ciz(() => {
    const seriler = veri.seriler.map((s, i) => ({
      type: 'bar', label: s.ad, data: s.veri.map(G.lira), stack: 'g',
      backgroundColor: G.renk('--k' + ((i % 8) + 1)), borderWidth: 0, maxBarThickness: 36,
    }));
    const ipucu = G.ipucu();
    ipucu.callbacks = {
      label: (c) => c.parsed.y ? `${c.dataset.label}: ${G.tl.format(c.parsed.y)}` : null,
      footer: (items) => 'Net toplam: ' + G.tl.format(items.reduce((t, c) => t + (c.parsed.y || 0), 0)),
    };
    return new Chart(el, {
      data: { labels: veri.aylar, datasets: seriler },
      options: { ...G.ortak, interaction: { mode: 'index', intersect: false },
        plugins: { tooltip: ipucu, legend: { position: 'top', align: 'start', labels: { usePointStyle: true, boxWidth: 8, padding: 14 } } },
        scales: { y: { ...G.eksenTL(), stacked: true, beginAtZero: true }, x: { stacked: true, grid: { display: false } } } },
    });
  });
})();
