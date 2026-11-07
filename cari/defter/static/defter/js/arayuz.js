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

  // Tablolar: ad (en yakın başlık) ve yatay kayan kutular klavyeyle odaklanıp kaydırılabilsin
  function tabloErisim() {
    document.querySelectorAll('.tablo-kaydir').forEach(function (k) {
      var t = k.querySelector('table');
      if (!t || t.getAttribute('aria-label') || t.querySelector('caption')) return;
      var kap = k.closest('.kart') || k.parentElement, h = null;
      for (var n = k.previousElementSibling; n && !h; n = n.previousElementSibling) if (/^H[1-3]$/.test(n.tagName)) h = n;
      if (!h && kap) h = kap.querySelector('h2, h3');
      if (!h) h = document.querySelector('h1');
      if (h) t.setAttribute('aria-label', h.textContent.trim());
    });
    document.querySelectorAll('.tablo-kaydir').forEach(function (k) {
      var kayar = k.scrollWidth > k.clientWidth + 1, t = k.querySelector('table');
      if (kayar) { k.tabIndex = 0; k.setAttribute('role', 'region'); if (t && t.getAttribute('aria-label')) k.setAttribute('aria-label', t.getAttribute('aria-label')); }
      else if (k.getAttribute('role') === 'region') { k.removeAttribute('tabindex'); k.removeAttribute('role'); k.removeAttribute('aria-label'); }
    });
  }
  tabloErisim();
  window.addEventListener('resize', tabloErisim);

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
