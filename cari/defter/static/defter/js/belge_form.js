// Fiş kalemleri: satır ekleme ve canlı toplam. Sunucu her şeyi yeniden doğrular; burası yalnızca kolaylık sağlar (JS yoksa form yine çalışır).
(function () {
  const govde = document.getElementById('kalem-govde');
  if (!govde) return;
  const sayac = document.getElementById('kalem-sayisi');
  const toplamEl = document.getElementById('kalem-toplam');
  const tl = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  // '1.234,50' -> 1234.5 ; geçersizse null
  function sayi(metin) {
    const m = (metin || '').trim().replace(/\s/g, '');
    if (!m || !/^(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$/.test(m)) return null;
    return parseFloat(m.replace(/\./g, '').replace(',', '.'));
  }
  function satirTutari(tr) {
    const girilen = sayi(tr.querySelector('[name^="kalem_tutar_"]').value);
    if (girilen !== null) return girilen;
    const miktar = tr.querySelector('[name^="kalem_miktar_"]').value.trim() === '' ? 1 : sayi(tr.querySelector('[name^="kalem_miktar_"]').value);
    const fiyat = sayi(tr.querySelector('[name^="kalem_fiyat_"]').value);
    return miktar !== null && fiyat !== null ? Math.round(miktar * fiyat * 100) / 100 : 0;
  }
  function topla() {
    let t = 0;
    govde.querySelectorAll('tr').forEach((tr) => { t += satirTutari(tr); });
    toplamEl.textContent = t > 0 ? tl.format(t) + ' ₺' : '—';
  }
  govde.addEventListener('input', topla);
  document.getElementById('kalem-ekle').addEventListener('click', () => {
    const son = govde.lastElementChild;
    const i = govde.children.length;
    const yeni = son.cloneNode(true);
    yeni.classList.remove('hatali');
    yeni.querySelectorAll('input').forEach((inp) => {
      inp.value = '';
      inp.name = inp.name.replace(/_\d+$/, '_' + i);
      inp.setAttribute('aria-label', inp.getAttribute('aria-label').replace(/Kalem \d+/, 'Kalem ' + (i + 1)));
    });
    govde.appendChild(yeni);
    sayac.value = govde.children.length;
    yeni.querySelector('input').focus();
  });
  topla();
})();
