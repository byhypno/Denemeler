(function () {
  const G = window.CariGrafik;
  const veri = JSON.parse(document.getElementById('grafik-veri').textContent);
  G.ciz(() => {
    const aylik = new Chart(document.getElementById('g-kasa-aylik'), {
      data: {
        labels: veri.aylar,
        datasets: [
          { type: 'bar', label: 'Giriş', data: veri.giris.map(G.lira), backgroundColor: G.renk('--g-alis'), borderRadius: 2 },
          { type: 'bar', label: 'Çıkış', data: veri.cikis.map(G.lira), backgroundColor: G.renk('--g-iade'), borderRadius: 2 },
          { type: 'line', label: 'Ay sonu kasa bakiyesi', data: veri.ay_sonu.map(G.lira),
            borderColor: G.renk('--g-bakiye'), backgroundColor: G.renk('--g-bakiye'), borderWidth: 2.5,
            pointRadius: 3, tension: 0, spanGaps: false },
        ],
      },
      options: { ...G.ortak, interaction: { mode: 'index', intersect: false },
        plugins: { tooltip: G.ipucu, legend: { position: 'top', align: 'start', labels: { usePointStyle: true, boxWidth: 8, padding: 16 } } },
        scales: { y: G.eksenTL(), x: { grid: { display: false } } } },
    });
    return [aylik, G.yatay('g-kasa-kategori', veri.kat_etiket, veri.kat_deger, 'Çıkış', '--g-iade')];
  });
})();
