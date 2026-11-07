// "Listedekilerin hepsini seç" kutusu (toplu kategori ataması için). JS yoksa tek tek işaretlenir.
(function () {
  var h = document.getElementById('tumunu-sec');
  if (!h) return;
  h.addEventListener('change', function () {
    document.querySelectorAll('input[name="sec"]').forEach(function (c) { c.checked = h.checked; });
  });
})();
