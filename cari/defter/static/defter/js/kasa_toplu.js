/* Toplu kasa girişi: Enter sonraki alana geçer, son alanda yeni satır açar; yeni satır tarih/yönü bir öncekinden alır. */
(function () {
  'use strict';
  const govde = document.getElementById('toplu-govde'), sayac = document.getElementById('satir-sayisi');
  if (!govde || !sayac) return;
  function satirEkle() {
    const satirlar = Array.from(govde.querySelectorAll('tr:not(.hatali-not)'));
    const son = satirlar[satirlar.length - 1], i = parseInt(sayac.value, 10) || satirlar.length;
    const yeni = son.cloneNode(true);
    yeni.classList.remove('hatali');
    yeni.querySelectorAll('.hata').forEach((e) => e.remove());
    yeni.querySelectorAll('input, select').forEach((alan) => {
      alan.name = alan.name.replace(/^s\d+-/, 's' + i + '-');
      alan.id = alan.id ? alan.id.replace(/^id_s\d+-/, 'id_s' + i + '-') : alan.id;
      const ad = alan.name.split('-')[1];
      if (ad !== 'tarih' && ad !== 'yon') alan.value = '';
    });
    govde.appendChild(yeni);
    sayac.value = i + 1;
    const ilk = yeni.querySelector('input:not([type=date]), select');
    (yeni.querySelector('input[name$="-tutar_kurus"]') || ilk).focus();
  }
  document.getElementById('toplu-ekle').addEventListener('click', satirEkle);
  govde.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.ctrlKey || e.altKey || e.isComposing || e.target.tagName === 'BUTTON') return;
    e.preventDefault();
    const alanlar = Array.from(govde.querySelectorAll('input, select'));
    const sira = alanlar.indexOf(e.target);
    if (sira < 0) return;
    if (sira === alanlar.length - 1) { satirEkle(); return; }
    alanlar[sira + 1].focus();
    if (alanlar[sira + 1].select) alanlar[sira + 1].select();
  });
})();
