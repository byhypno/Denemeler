(function () {
  const G = window.CariGrafik;
  const veri = JSON.parse(document.getElementById('grafik-veri').textContent);

  G.ciz(() => {
    const aylik = new Chart(document.getElementById('g-aylik'), {
      data: {
        labels: veri.aylar,
        datasets: [
          { type: 'bar', label: 'Alış', data: veri.alis.map(G.lira), backgroundColor: G.renk('--g-alis'), borderRadius: 5, borderSkipped: false, maxBarThickness: 18 },
          { type: 'bar', label: 'Ödeme', data: veri.odeme.map(G.lira), backgroundColor: G.renk('--g-odeme'), borderRadius: 5, borderSkipped: false, maxBarThickness: 18 },
          { type: 'bar', label: 'İade', data: veri.iade.map(G.lira), backgroundColor: G.renk('--g-iade'), borderRadius: 5, borderSkipped: false, maxBarThickness: 18 },
          { type: 'line', label: 'Ay sonu bakiye', data: veri.ay_sonu.map(G.lira), borderColor: G.renk('--g-bakiye'), borderWidth: 2.5, pointRadius: 3, pointHoverRadius: 5, tension: 0.3, fill: true, backgroundColor: G.alanDolgu('--g-bakiye'), spanGaps: false },
        ],
      },
      options: { ...G.ortak, interaction: { mode: 'index', intersect: false },
        plugins: { tooltip: G.ipucu(), legend: { position: 'top', align: 'start', labels: { usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 22 } } },
        scales: { y: G.eksenTL(), x: { grid: { display: false } } } },
    });
    const yas = new Chart(document.getElementById('g-yas'), {
      type: 'bar',
      data: { labels: veri.yas_etiket, datasets: [{ label: 'Açık borç', data: veri.yas_deger.map(G.lira),
        backgroundColor: G.renk('--g-odeme'), borderRadius: 6, borderSkipped: false, maxBarThickness: 40 }] },
      options: { ...G.ortak, plugins: { legend: { display: false }, tooltip: G.ipucu() },
        scales: { y: G.eksenTL(), x: { grid: { display: false } } } },
    });
    return [aylik, yas,
      G.yatay('g-borclu', veri.borclu_etiket, veri.borclu_deger, 'Borç', '--g-odeme'),
      G.yatay('g-kalem', veri.kalem_etiket, veri.kalem_deger, 'Alış tutarı', '--g-alis')];
  });
})();
