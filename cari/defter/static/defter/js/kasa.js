(function () {
  const G = window.CariGrafik;
  const veri = JSON.parse(document.getElementById('grafik-veri').textContent);
  new Chart(document.getElementById('g-kasa-aylik'), {
    data: {
      labels: veri.aylar,
      datasets: [
        { type: 'bar', label: 'Giriş', data: veri.giris.map(G.lira), backgroundColor: G.renk('--iade') },
        { type: 'bar', label: 'Çıkış', data: veri.cikis.map(G.lira), backgroundColor: G.renk('--odeme') },
        { type: 'line', label: 'Ay sonu kasa bakiyesi', data: veri.ay_sonu.map(G.lira),
          borderColor: G.renk('--bakiye'), backgroundColor: G.renk('--bakiye'), borderWidth: 2.5,
          pointRadius: 3, tension: 0, spanGaps: false },
      ],
    },
    options: { ...G.ortak, interaction: { mode: 'index', intersect: false },
      plugins: { tooltip: G.ipucu, legend: { position: 'top', labels: { usePointStyle: true } } },
      scales: { y: G.eksenTL, x: { grid: { display: false } } } },
  });
  G.yatay('g-kasa-kategori', veri.kat_etiket, veri.kat_deger, 'Çıkış', '--odeme');
})();
