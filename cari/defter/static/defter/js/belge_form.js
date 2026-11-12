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
  // Kalem tutarı = miktar × birim fiyat (kuruşa yarım yukarı yuvarlanır; sunucudaki hesapla birebir aynı). Tamsayı/BigInt ile: kayan nokta hatası olmaz.
  function olcekli(metin, kesir) {            // '1.234,5' -> BigInt (10^kesir ile ölçekli); geçersizse null
    const m = (metin || '').trim().replace(/\s/g, '');
    if (!m || !/^(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$/.test(m)) return null;
    const [tam, k = ''] = m.replace(/\./g, '').split(',');
    if (k.length > kesir) return null;
    return BigInt(tam + k.padEnd(kesir, '0'));
  }
  function satirKurus(tr) {
    const mk = tr.querySelector('[name^="kalem_miktar_"]').value.trim();
    const miktar = mk === '' ? 1000n : olcekli(mk, 3);
    const fiyat = olcekli(tr.querySelector('[name^="kalem_fiyat_"]').value, 4);
    if (miktar === null || fiyat === null || miktar <= 0n || fiyat <= 0n) return null;
    return (miktar * fiyat + 50000n) / 100000n;
  }
  function satirTutari(tr) {
    const kutu = tr.querySelector('[name^="kalem_tutar_"]');
    const kurus = satirKurus(tr);
    kutu.value = kurus === null ? '' : tl.format(Number(kurus) / 100);
    return kurus === null ? 0 : Number(kurus) / 100;
  }
  function topla() {
    let t = 0;
    govde.querySelectorAll('tr').forEach((tr) => { t += satirTutari(tr); });
    toplamEl.textContent = t > 0 ? tl.format(t) + ' ₺' : '—';
  }
  // ---- fiyat hafızası: malzemenin son alış fiyatını hatırlat, yeni fiyat yüksekse uyar (sunucu kayıttan sonra da ayrıca uyarır)
  const hafizaEl = document.getElementById('malzeme-hafiza');
  const hafiza = new Map();
  const katla = (s) => (s || '').replace(/İ/g, 'i').replace(/I/g, 'i').toLowerCase()
    .replace(/ı/g, 'i').replace(/ş/g, 's').replace(/ğ/g, 'g').replace(/ü/g, 'u').replace(/ö/g, 'o').replace(/ç/g, 'c').replace(/\s+/g, ' ').trim();
  if (hafizaEl) JSON.parse(hafizaEl.textContent).forEach((m) => hafiza.set(katla(m.ad), m));
  const tl4 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });   // birim fiyat 4 haneye kadar (0,335)
  const lira = (n) => tl4.format(n) + ' ₺';
  function birimFiyat(tr) {
    const f = sayi(tr.querySelector('[name^="kalem_fiyat_"]').value);
    if (f !== null) return f;
    return null;
  }
  function ipucu(tr) {
    const kutu = tr.querySelector('.kalem-ipucu');
    if (!kutu) return;
    const m = hafiza.get(katla(tr.querySelector('[name^="kalem_aciklama_"]').value));
    kutu.replaceChildren();
    if (!m) return;
    if (m.fiyat === undefined) { kutu.textContent = 'Katalogda var, henüz alış kaydı yok.'; return; }
    const son = parseFloat(m.fiyat);        // hafıza verisi LİRA cinsindendir
    const yazi = document.createElement('span');
    yazi.textContent = 'Son alış: ' + lira(son) + (m.birim ? ' / ' + m.birim : '') + ' · ' + m.tarih + ' · ' + m.cari + ' ';
    kutu.appendChild(yazi);
    const yeni = birimFiyat(tr);
    if (yeni !== null && son > 0 && Math.abs(yeni - son) >= 0.005) {     // son fiyat 0 ise oran tanımsız (Infinity olmasın)
      const oran = ((yeni - son) / son) * 100;
      const chip = document.createElement('span');
      chip.className = 'degisim ' + (oran > 0 ? 'kotu' : 'iyi');
      chip.textContent = (oran > 0 ? '▲ %' : '▼ %') + Math.abs(oran).toFixed(1).replace('.', ',') + (oran > 0 ? ' zam' : ' indirim');
      kutu.appendChild(chip);
    } else if (yeni === null && son > 0) {
      const d = document.createElement('button');
      d.type = 'button'; d.className = 'kucuk ikincil dugme'; d.textContent = 'Son fiyatı kullan';
      d.addEventListener('click', () => {
        tr.querySelector('[name^="kalem_fiyat_"]').value = tl4.format(son);
        const b = tr.querySelector('[name^="kalem_birim_"]'); if (b && !b.value && m.birim) b.value = m.birim;
        topla(); ipucu(tr);
      });
      kutu.appendChild(d);
    }
  }
  govde.addEventListener('input', (e) => { topla(); ipucu(e.target.closest('tr')); });
  govde.addEventListener('change', (e) => { ipucu(e.target.closest('tr')); });
  govde.querySelectorAll('tr').forEach(ipucu);
  function satirEkle() {
    const son = govde.lastElementChild;
    const i = govde.children.length;
    const yeni = son.cloneNode(true);
    yeni.classList.remove('hatali');
    yeni.querySelector('.kalem-ipucu') && yeni.querySelector('.kalem-ipucu').replaceChildren();
    yeni.querySelectorAll('input').forEach((inp) => {
      inp.value = '';
      inp.name = inp.name.replace(/_\d+$/, '_' + i);
      inp.setAttribute('aria-label', inp.getAttribute('aria-label').replace(/Kalem \d+/, 'Kalem ' + (i + 1)));
    });
    govde.appendChild(yeni);
    sayac.value = govde.children.length;
    yeni.querySelector('input').focus();
  }
  document.getElementById('kalem-ekle').addEventListener('click', satirEkle);
  // Klavye akışı: kalem alanında Enter formu göndermez; sonraki alana (satır sonunda sonraki satıra, en sonda yeni satıra) geçer.
  govde.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.ctrlKey || e.altKey || e.isComposing || e.target.tagName !== 'INPUT') return;
    e.preventDefault();
    const alanlar = Array.from(govde.querySelectorAll('input:not([readonly])'));
    const sira = alanlar.indexOf(e.target);
    if (sira < 0) return;
    if (sira === alanlar.length - 1) { satirEkle(); return; }
    alanlar[sira + 1].focus();
    if (alanlar[sira + 1].select) alanlar[sira + 1].select();
  });
  topla();
})();
