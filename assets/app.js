(() => {
  'use strict';

  // ---------- Configuración ----------
  const URL_FUEGO   = 'api/fuego.php';
  const URL_ALERTAS = 'api/alertas.php';

  // ---------- Mapa (OpenStreetMap + Leaflet) ----------
  const map = L.map('map').setView([-33.3, -66.3], 6);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(map);

  const capaFuego   = L.layerGroup().addTo(map);
  const capaAlertas = L.layerGroup();
  let marcadorSel = null;

  // ---------- Utilidades ----------
  const $ = id => document.getElementById(id);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();

  function hoyLocal() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  function setEstado(el, msg, error = false) {
    el.textContent = msg;
    el.classList.toggle('error', error);
  }

  function validarFechas(desde, hasta, el) {
    if (!desde || !hasta) { setEstado(el, 'Ingrese fecha desde y fecha hasta.', true); return false; }
    if (desde > hasta)    { setEstado(el, 'La fecha desde no puede ser mayor que la fecha hasta.', true); return false; }
    return true;
  }

  // Parser CSV (soporta comillas y separador , o ;)
  function parseCSV(texto) {
    texto = texto.replace(/^\uFEFF/, '').trim();
    if (!texto) return [];
    const primera = texto.split(/\r?\n/)[0];
    const sep = (primera.match(/;/g) || []).length > (primera.match(/,/g) || []).length ? ';' : ',';

    const filas = [];
    let fila = [], campo = '', comillas = false;
    for (let i = 0; i < texto.length; i++) {
      const c = texto[i];
      if (comillas) {
        if (c === '"' && texto[i + 1] === '"') { campo += '"'; i++; }
        else if (c === '"') comillas = false;
        else campo += c;
      } else if (c === '"') comillas = true;
      else if (c === sep) { fila.push(campo); campo = ''; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && texto[i + 1] === '\n') i++;
        fila.push(campo); campo = '';
        if (fila.some(x => x !== '')) filas.push(fila);
        fila = [];
      } else campo += c;
    }
    fila.push(campo);
    if (fila.some(x => x !== '')) filas.push(fila);

    const cab = filas.shift().map(norm);
    return filas.map(f => Object.fromEntries(cab.map((h, i) => [h, (f[i] ?? '').trim()])));
  }

  function buscar(obj, candidatos) {
    for (const k of candidatos) if (obj[k] !== undefined && obj[k] !== '') return obj[k];
    return '';
  }
  const getLat = r => parseFloat(buscar(r, ['latitud', 'latitude', 'lat']).replace(',', '.'));
  const getLon = r => parseFloat(buscar(r, ['longitud', 'longitude', 'lon', 'lng', 'long']).replace(',', '.'));

  async function pedirCSV(url, desde, hasta) {
    const q = new URLSearchParams({ fecha_desde: desde, fecha_hasta: hasta });
    const resp = await fetch(`${url}?${q}`, { headers: { 'Accept': 'text/csv' } });
    if (!resp.ok) throw new Error(`Error del servidor (${resp.status})`);
    return parseCSV(await resp.text());
  }

  // ---------- Tabs ----------
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
      $('tab-' + btn.dataset.tab).classList.add('active');

      if (btn.dataset.tab === 'fuego') { map.removeLayer(capaAlertas); map.addLayer(capaFuego); }
      else                             { map.removeLayer(capaFuego);   map.addLayer(capaAlertas); }
    });
  });

  // ---------- Tab 1: Información de fuego ----------
  async function cargarFuego(desde, hasta) {
    const estado = $('fuegoEstado');
    if (!validarFechas(desde, hasta, estado)) return;

    const btns = [$('btnHoy'), $('btnFuego')];
    btns.forEach(b => b.disabled = true);
    setEstado(estado, 'Cargando…');
    capaFuego.clearLayers();

    try {
      const filas = await pedirCSV(URL_FUEGO, desde, hasta);
      const puntos = [];

      filas.forEach(r => {
        const lat = getLat(r), lon = getLon(r);
        if (isNaN(lat) || isNaN(lon)) return;
        const detalle = Object.entries(r)
          .map(([k, v]) => `<b>${esc(k)}:</b> ${esc(v)}`).join('<br>');
        L.circleMarker([lat, lon], {
          radius: 6, color: '#a61e00', weight: 1, fillColor: '#ff6a00', fillOpacity: .85
        }).bindPopup(detalle).addTo(capaFuego);
        puntos.push([lat, lon]);
      });

      if (puntos.length) {
        map.fitBounds(L.latLngBounds(puntos).pad(0.2), { maxZoom: 12 });
        setEstado(estado, `${puntos.length} punto(s) encontrados.`);
      } else {
        setEstado(estado, 'No se encontraron puntos para el rango indicado.');
      }
    } catch (e) {
      setEstado(estado, e.message, true);
    } finally {
      btns.forEach(b => b.disabled = false);
    }
  }

  $('btnHoy').addEventListener('click', () => {
    const hoy = hoyLocal();
    $('fuegoDesde').value = hoy;
    $('fuegoHasta').value = hoy;
    cargarFuego(hoy, hoy);
  });
  $('btnFuego').addEventListener('click', () => cargarFuego($('fuegoDesde').value, $('fuegoHasta').value));

  // ---------- Tab 2: Alertas enviadas ----------
  const claseAlerta = txt => {
    const t = norm(txt);
    return t.includes('roja') ? 'roja' : t.includes('amarilla') ? 'amarilla' : 'otra';
  };
  const colorAlerta = c => c === 'roja' ? '#e03131' : c === 'amarilla' ? '#f5b800' : '#4c6ef5';

  async function cargarAlertas() {
    const desde = $('alertaDesde').value, hasta = $('alertaHasta').value;
    const estado = $('alertaEstado');
    if (!validarFechas(desde, hasta, estado)) return;

    const btn = $('btnAlertas');
    const tbody = document.querySelector('#tablaAlertas tbody');
    btn.disabled = true;
    setEstado(estado, 'Cargando…');
    tbody.innerHTML = '';
    capaAlertas.clearLayers();
    marcadorSel = null;

    try {
      const filas = await pedirCSV(URL_ALERTAS, desde, hasta);
      let n = 0;

      filas.forEach(r => {
        const lat = getLat(r), lon = getLon(r);
        const fecha = buscar(r, ['fecha']);
        const hora = buscar(r, ['hora']);
        const alerta = buscar(r, ['alerta', 'nivel', 'tipo']);
        const clase = claseAlerta(alerta);
        const tieneCoord = !isNaN(lat) && !isNaN(lon);

        let marcador = null;
        if (tieneCoord) {
          marcador = L.circleMarker([lat, lon], {
            radius: 8, color: '#222', weight: 1, fillColor: colorAlerta(clase), fillOpacity: .9
          }).bindPopup(`<b>${esc(alerta)}</b><br>${esc(fecha)} ${esc(hora)}<br>${lat.toFixed(5)}, ${lon.toFixed(5)}`)
            .addTo(capaAlertas);
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${esc(fecha)}</td>
          <td>${esc(hora)}</td>
          <td><span class="badge ${clase}">${esc(alerta)}</span></td>
          <td>${tieneCoord ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : '—'}</td>`;

        if (marcador) {
          tr.addEventListener('click', () => {
            tbody.querySelectorAll('tr.sel').forEach(x => x.classList.remove('sel'));
            tr.classList.add('sel');
            if (marcadorSel) marcadorSel.setStyle({ weight: 1, radius: 8 });
            marcadorSel = marcador;
            marcador.setStyle({ weight: 3, radius: 11 }).bringToFront();
            map.setView([lat, lon], Math.max(map.getZoom(), 13));
            marcador.openPopup();
          });
        }
        tbody.appendChild(tr);
        n++;
      });

      setEstado(estado, n ? `${n} alerta(s) encontradas. Haga clic en una fila para verla en el mapa.` : 'No hay alertas en el rango indicado.');

      const pts = capaAlertas.getLayers().map(l => l.getLatLng());
      if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.2), { maxZoom: 12 });
    } catch (e) {
      setEstado(estado, e.message, true);
    } finally {
      btn.disabled = false;
    }
  }
  $('btnAlertas').addEventListener('click', cargarAlertas);
})();
