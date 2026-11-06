// Panolar arasında paylaşılan grafik yardımcıları (Chart.js yerel kopyası gerekir).
// Renkler CSS token'larından okunur (--g-*, --murekkep-2...) ve tema değişince grafikler yeniden çizilir.
window.CariGrafik = (function () {
  const tl = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 2 });
  const tam = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
  // Tutarlar veritabanında kuruştur; grafik yalnızca GÖSTERİM için liraya çevirir.
  const lira = (kurus) => (kurus === null ? null : kurus / 100);
  const renk = (ad) => getComputedStyle(document.documentElement).getPropertyValue(ad).trim();

  function varsayilanlar() {
    Chart.defaults.font.family = renk('--font-ui') || 'system-ui, sans-serif';
    Chart.defaults.font.size = 12.5;
    Chart.defaults.color = renk('--murekkep-2');
    Chart.defaults.borderColor = renk('--g-izgara');
    Chart.defaults.animation = false;
  }
  const eksenTL = () => ({ ticks: { callback: (v) => tam.format(v) + ' ₺', maxTicksLimit: 7, maxRotation: 0 },
    grid: { color: renk('--g-izgara') }, border: { display: false } });
  const ipucu = { callbacks: { label: (c) => `${c.dataset.label || c.label}: ${tl.format(c.parsed.y ?? c.parsed.x)}` } };
  const ortak = { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 8 } } };

  function yatay(id, etiket, deger, ad, renkAdi) {
    const el = document.getElementById(id);
    if (!el) return null;
    const kisalt = (k) => (k.length > 24 ? k.slice(0, 23) + '…' : k);
    return new Chart(el, {
      type: 'bar',
      data: { labels: etiket.map(kisalt),
        datasets: [{ label: ad, data: deger.map(lira), backgroundColor: renk(renkAdi || '--g-odeme'),
          borderRadius: 3, maxBarThickness: 28 }] },
      options: { ...ortak, indexAxis: 'y',
        plugins: { legend: { display: false },
          tooltip: { callbacks: { title: (c) => etiket[c[0].dataIndex], label: (c) => `${ad}: ${tl.format(c.parsed.x)}` } } },
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

  return { renk, tl, tam, lira, eksenTL, ipucu, ortak, yatay, ciz };
})();
