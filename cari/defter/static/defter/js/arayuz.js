// Tema (açık/koyu) ve mobil menü çekmecesi. Dışarıdan hiçbir kaynak yüklenmez.
(function () {
  var html = document.documentElement;
  var sistemKoyu = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function gecerliTema() {
    return html.dataset.tema || (sistemKoyu && sistemKoyu.matches ? 'koyu' : 'acik');
  }
  function dugmeyiGuncelle() {
    var d = document.getElementById('tema-dugme');
    if (!d) return;
    var koyu = gecerliTema() === 'koyu';
    d.setAttribute('aria-label', koyu ? 'Açık temaya geç' : 'Koyu temaya geç');
    var et = d.querySelector('.tema-etiket'); if (et) et.textContent = koyu ? 'Açık tema' : 'Koyu tema';
    var u = d.querySelector('use'); if (u) u.setAttribute('href', koyu ? '#i-gunes' : '#i-ay');
  }
  function temaUygula(t) {
    html.dataset.tema = t;
    try { localStorage.setItem('cari_tema', t); } catch (e) {}
    dugmeyiGuncelle();
    document.dispatchEvent(new CustomEvent('tema-degisti', { detail: t }));   // grafikler yeniden çizilir
  }
  var tema = document.getElementById('tema-dugme');
  if (tema) tema.addEventListener('click', function () { temaUygula(gecerliTema() === 'koyu' ? 'acik' : 'koyu'); });
  if (sistemKoyu && sistemKoyu.addEventListener) sistemKoyu.addEventListener('change', function () {
    if (!html.dataset.tema) { dugmeyiGuncelle(); document.dispatchEvent(new CustomEvent('tema-degisti')); }
  });
  dugmeyiGuncelle();

  // mobil çekmece
  var kabuk = document.getElementById('kabuk'), ac = document.getElementById('yan-ac'), yan = document.getElementById('yan');
  if (!kabuk || !ac || !yan) return;
  function ayarla(acik) {
    kabuk.classList.toggle('yan-acik', acik);
    ac.setAttribute('aria-expanded', acik ? 'true' : 'false');
    ac.setAttribute('aria-label', acik ? 'Menüyü kapat' : 'Menüyü aç');
    var ana = document.getElementById('icerik');
    if (ana) ana.inert = acik;                       // çekmece açıkken arka plan Tab ile erişilemez (odak çekmecede kalır)
    if (acik) { var ilk = yan.querySelector('a, button'); if (ilk) ilk.focus(); } else { ac.focus(); }
  }
  ac.addEventListener('click', function () { ayarla(!kabuk.classList.contains('yan-acik')); });
  document.addEventListener('click', function (e) { if (e.target.hasAttribute && e.target.hasAttribute('data-yan-kapat')) ayarla(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && kabuk.classList.contains('yan-acik')) ayarla(false); });
})();
