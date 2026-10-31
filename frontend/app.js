// Naqsha AI dashboard
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const jsq = (s) => JSON.stringify(String(s ?? '')).replace(/"/g, '&quot;');  // string literal safe inside onclick="..."
const COLORS = {high: '#d93025', medium: '#f29900', low: '#188038'};
const LAYER_COLORS = ['#1a73e8', '#a142f4', '#e8710a', '#12b5cb', '#e52592', '#188038', '#f9ab00'];
const state = {hazards: {}, markers: {}, layers: [], selected: null, pickMode: false, repLoc: null, teams: [], me: null};
const ms = (name) => `<span class="ms">${name}</span>`;

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
const post = (path, body) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
const loading = (el, msg) => el.innerHTML = `<div class="box"><span class="spin"></span>${esc(msg)}<div class="skel"></div><div class="skel" style="width:70%"></div></div>`;
const fail = (el, e) => el.innerHTML = `<div class="box err">${ms('error')} ${esc(e.message || e)}</div>`;

function toast(msg, color, ms_ = 5000) {
  const t = $('#toast'); t.textContent = msg; t.style.background = color || '#323232'; t.style.display = 'block';
  clearTimeout(t._h); t._h = setTimeout(() => t.style.display = 'none', ms_);
}
function beep() {
  try { const c = new AudioContext(), o = c.createOscillator(), g = c.createGain();
    o.frequency.value = 880; o.connect(g); g.connect(c.destination); g.gain.value = .15; o.start();
    setTimeout(() => { o.frequency.value = 660; }, 160); setTimeout(() => { o.stop(); c.close(); }, 380); } catch (e) {}
}
function speak(text, lang) {
  if (!text || !window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang || 'ur-PK';
  const v = speechSynthesis.getVoices().find(v => v.lang.startsWith(u.lang.slice(0, 2)));
  if (v) u.voice = v;
  speechSynthesis.speak(u);
}
window.speak = speak; window.toast = toast;
function feed(msg) {
  const f = $('#feed'); if (f.querySelector('p.hint')) f.innerHTML = '';
  const d = document.createElement('div');
  d.innerHTML = `<span class="hint">${new Date().toLocaleTimeString()}</span> ${msg}`; f.prepend(d);
}
const debounce = (fn, ms_) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms_); }; };
const fmtKm = (km) => km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(km < 10 ? 2 : 1)} km`;
const fmtH = (h) => { const m = Math.round(h * 60); return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`; };

// ---------- map ----------
const map = L.map('map', {zoomControl: false, zoomSnap: 0.25, zoomDelta: 0.5, wheelPxPerZoomLevel: 90,
  wheelDebounceTime: 30, minZoom: 4, maxZoom: 20}).setView([34.6, 73.0], 7);
L.control.zoom({position: 'bottomright'}).addTo(map);
L.control.scale({position: 'bottomright', imperial: false}).addTo(map);

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';
const BASES = {
  map: L.tileLayer(`${ESRI}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`,
    {maxZoom: 20, maxNativeZoom: 19, attribution: 'Tiles © Esri, HERE, Garmin, © OpenStreetMap contributors'}),
  sat: L.layerGroup([
    L.tileLayer(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, {maxZoom: 20, maxNativeZoom: 19, attribution: 'Imagery © Esri, Maxar, Earthstar Geographics'}),
    L.tileLayer(`${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`, {maxZoom: 20, maxNativeZoom: 19, opacity: .75}),
    L.tileLayer(`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, {maxZoom: 20, maxNativeZoom: 19})]),
  terrain: L.tileLayer(`${ESRI}/World_Topo_Map/MapServer/tile/{z}/{y}/{x}`, {maxZoom: 20, maxNativeZoom: 19, attribution: 'Tiles © Esri'}),
  dark: L.layerGroup([
    L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, {maxZoom: 20, maxNativeZoom: 16, attribution: 'Tiles © Esri'}),
    L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, {maxZoom: 20, maxNativeZoom: 16})]),
  osm: L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 20, maxNativeZoom: 19, attribution: '© OpenStreetMap contributors'}),
};
let base = 'map';
function setBase(name) {
  if (!BASES[name]) return;
  map.removeLayer(BASES[base]); base = name; BASES[name].addTo(map);
  document.querySelectorAll('.mt').forEach(b => b.classList.toggle('on', b.dataset.base === name));
  saveView();
}
document.querySelectorAll('.mt').forEach(b => b.onclick = () => setBase(b.dataset.base));

const hazLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);
const exposureLayer = L.layerGroup().addTo(map);
const placeLayer = L.layerGroup().addTo(map);
let rainLayer = null, pickMarker = null;

// view in the URL (#lat,lon,zoom,base) so a link opens the same view
function saveView() {
  const c = map.getCenter();
  history.replaceState(null, '', `#${c.lat.toFixed(5)},${c.lng.toFixed(5)},${map.getZoom()}z,${base}`);
}
(function loadView() {
  const m = location.hash.match(/^#(-?[\d.]+),(-?[\d.]+),([\d.]+)z?(?:,(\w+))?/);
  if (m) { map.setView([+m[1], +m[2]], +m[3]); if (m[4] && BASES[m[4]]) base = m[4]; }
  BASES[base].addTo(map);
  document.querySelectorAll('.mt').forEach(b => b.classList.toggle('on', b.dataset.base === base));
})();
map.on('moveend', saveView);
map.on('mousemove', (e) => { $('#mcoords').textContent = `${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`; });

// overlays
$('#ovHaz').onchange = (e) => e.target.checked ? hazLayer.addTo(map) : map.removeLayer(hazLayer);
$('#ovRoute').onchange = (e) => e.target.checked ? routeLayer.addTo(map) : map.removeLayer(routeLayer);
$('#ovRain').onchange = async (e) => {
  if (!e.target.checked) { if (rainLayer) map.removeLayer(rainLayer); return; }
  try {
    const j = await (await fetch('https://api.rainviewer.com/public/weather-maps.json')).json();
    const f = j.radar.past[j.radar.past.length - 1];
    if (rainLayer) map.removeLayer(rainLayer);
    rainLayer = L.tileLayer(`${j.host}${f.path}/256/{z}/{x}/{y}/2/1_1.png`, {opacity: .65, maxNativeZoom: 7, maxZoom: 20,
      attribution: 'Rain radar © RainViewer'}).addTo(map);
    toast(`Rain radar: ${new Date(f.time * 1000).toLocaleTimeString()}`, '#1a73e8');
  } catch (err) { e.target.checked = false; toast('Rain radar is not available right now'); }
};

// tools: my location, measure, share, full screen
let meMarker = null, meCircle = null;
function locate(fly = true) {
  return new Promise((res, rej) => {
    if (!navigator.geolocation) return rej(new Error('Location is not supported by this browser'));
    navigator.geolocation.getCurrentPosition(p => {
      const ll = [p.coords.latitude, p.coords.longitude]; state.me = {lat: ll[0], lon: ll[1]};
      if (meMarker) { meMarker.remove(); meCircle.remove(); }
      meCircle = L.circle(ll, {radius: p.coords.accuracy, color: '#4285f4', weight: 1, fillOpacity: .12}).addTo(map);
      meMarker = L.marker(ll, {icon: L.divIcon({className: '', html: '<div class="me-dot"></div>', iconSize: [16, 16], iconAnchor: [8, 8]})})
        .addTo(map).bindTooltip('You are here');
      if (fly) map.flyTo(ll, Math.max(map.getZoom(), 15), {duration: 1.2});
      res(state.me);
    }, e => rej(new Error('Location not available: ' + e.message)), {enableHighAccuracy: true, timeout: 12000});
  });
}
$('#tLocate').onclick = () => locate().catch(e => toast(e.message));

let measuring = false, mPts = [], mLine = null, mDots = L.layerGroup().addTo(map);
function measureRender() {
  if (mLine) mLine.remove();
  mLine = L.polyline(mPts, {color: '#1a73e8', weight: 3, dashArray: '6 6'}).addTo(map);
  let d = 0; for (let i = 1; i < mPts.length; i++) d += map.distance(mPts[i - 1], mPts[i]);
  $('#measureBox').innerHTML = `${ms('straighten')} <b>${fmtKm(d / 1000)}</b> <span class="hint">click the map to add points</span>
    <button class="ghost" onclick="measureStop()">Done</button>`;
}
window.measureStop = () => {
  measuring = false; mPts = []; mDots.clearLayers(); if (mLine) { mLine.remove(); mLine = null; }
  $('#measureBox').hidden = true; $('#tMeasure').classList.remove('on'); map.getContainer().style.cursor = '';
};
$('#tMeasure').onclick = () => {
  if (measuring) return measureStop();
  measuring = true; $('#tMeasure').classList.add('on'); $('#measureBox').hidden = false; map.getContainer().style.cursor = 'crosshair';
  measureRender();
};
$('#tShare').onclick = async () => {
  try { await navigator.clipboard.writeText(location.href); toast('Link to this map view copied', '#1a73e8'); }
  catch (e) { prompt('Copy this link', location.href); }
};
$('#tFull').onclick = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
document.addEventListener('fullscreenchange', () => {
  $('#tFull').innerHTML = ms(document.fullscreenElement ? 'fullscreen_exit' : 'fullscreen'); setTimeout(() => map.invalidateSize(), 200);
});

map.on('click', (e) => {
  if (measuring) { mPts.push(e.latlng); L.circleMarker(e.latlng, {radius: 5, color: '#1a73e8', fillColor: '#fff', fillOpacity: 1, weight: 2}).addTo(mDots); measureRender(); return; }
  if (!state.pickMode) return;
  setReportLocation(e.latlng.lat, e.latlng.lng);
  state.pickMode = false; map.getContainer().style.cursor = '';
});

// ---------- place search (Google-Maps style) ----------
function placeIcon() { return L.divIcon({className: '', html: '<div class="place-pin"></div>', iconSize: [28, 28], iconAnchor: [14, 32], popupAnchor: [0, -30]}); }
function acAttach(input, list, onPick) {
  let items = [], sel = -1;
  const render = () => {
    list.innerHTML = items.map((p, i) => `<div class="ac-item ${i === sel ? 'sel' : ''}" data-i="${i}">${ms(p.icon || 'location_on')}<div><b>${esc(p.name)}</b><small>${esc(p.address || p.type || '')}</small></div></div>`).join('');
    list.classList.toggle('show', items.length > 0);
    list.querySelectorAll('.ac-item').forEach(el => el.onmousedown = (ev) => { ev.preventDefault(); pick(+el.dataset.i); });
  };
  const pick = (i) => { const p = items[i]; if (!p) return; items = []; render(); onPick(p); };
  const run = debounce(async () => {
    const q = input.value.trim(); if (q.length < 2) { items = []; render(); return; }
    const c = map.getCenter();
    try { items = await api(`/api/search?q=${encodeURIComponent(q)}&lat=${c.lat}&lon=${c.lng}`); } catch (e) { items = []; }
    if (state.me && 'my location'.startsWith(q.toLowerCase())) items.unshift({name: 'Your location', address: `${state.me.lat.toFixed(5)}, ${state.me.lon.toFixed(5)}`, lat: state.me.lat, lon: state.me.lon, icon: 'my_location'});
    sel = -1; render();
  }, 280);
  input.addEventListener('input', run);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sel = Math.min(items.length - 1, sel + 1); render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); render(); e.preventDefault(); }
    else if (e.key === 'Enter' && items.length) { pick(sel < 0 ? 0 : sel); e.preventDefault(); }
    else if (e.key === 'Escape') { items = []; render(); }
  });
  input.addEventListener('blur', () => setTimeout(() => { items = []; render(); }, 150));
}
acAttach($('#mq'), $('#mqList'), (p) => { $('#mq').value = p.name; $('#mqClear').hidden = false; showPlace(p); });
$('#mq').addEventListener('input', () => { $('#mqClear').hidden = !$('#mq').value; });
$('#mqClear').onclick = () => { $('#mq').value = ''; $('#mqClear').hidden = true; placeLayer.clearLayers(); };

function placeActions(lat, lon, name) {
  const n = jsq(name);
  return `<div class="row">
    <button class="ghost" onclick="routeTo(${lat},${lon},${n})">${ms('directions')}Directions</button>
    <button class="ghost" onclick="routeFrom(${lat},${lon},${n})">${ms('trip_origin')}From here</button>
    <button class="ghost" onclick="nearbyHelp(${lat},${lon})">${ms('local_hospital')}Nearby help</button>
    <button class="ghost" onclick="reportHere(${lat},${lon})">${ms('add_a_photo')}Report here</button>
    <a class="ghost btn" target="_blank" href="https://www.google.com/maps/search/?api=1&query=${lat},${lon}">${ms('open_in_new')}Google Maps</a>
  </div>`;
}
function showPlace(p) {
  placeLayer.clearLayers();
  if (p.extent) map.flyToBounds([[p.extent[3], p.extent[0]], [p.extent[1], p.extent[2]]], {maxZoom: 16, duration: 1.2});
  else map.flyTo([p.lat, p.lon], 15, {duration: 1.2});
  L.marker([p.lat, p.lon], {icon: placeIcon()}).addTo(placeLayer)
    .bindPopup(`<div class="pop"><h5>${esc(p.name)}</h5><div class="addr">${esc(p.address || '')}</div>
      <div class="coords">${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}</div><div class="wx" id="wx"></div>${placeActions(p.lat, p.lon, p.name)}</div>`).openPopup();
  loadWeather(p.lat, p.lon);
}

// right-click: what's here?
map.on('contextmenu', async (e) => {
  const {lat, lng} = e.latlng;
  const pop = L.popup().setLatLng(e.latlng).setContent(`<div class="pop"><h5>Dropped pin</h5><div class="addr" id="rgAddr"><span class="spin"></span>Finding address…</div>
    <div class="coords">${lat.toFixed(5)}, ${lng.toFixed(5)} <a href="#" onclick="navigator.clipboard.writeText('${lat.toFixed(6)}, ${lng.toFixed(6)}');toast('Coordinates copied','#1a73e8');return false">copy</a></div>
    <div class="wx" id="wx"></div>${placeActions(lat, lng, `${lat.toFixed(5)}, ${lng.toFixed(5)}`)}</div>`).openOn(map);
  loadWeather(lat, lng);
  try { const r = await api(`/api/reverse?lat=${lat}&lon=${lng}`); const el = document.getElementById('rgAddr'); if (el) el.textContent = r.address; }
  catch (err) { const el = document.getElementById('rgAddr'); if (el) el.textContent = ''; }
});
async function loadWeather(lat, lon) {
  try {
    const w = await api(`/api/weather?lat=${lat}&lon=${lon}`); const el = document.getElementById('wx'); if (!el) return;
    const rain = (w.daily.precipitation_sum || []).reduce((a, b) => a + (b || 0), 0);
    el.innerHTML = `<span>${ms('thermostat')} ${Math.round(w.current.temperature_2m)}°C</span><span>${ms('rainy')} ${rain.toFixed(1)} mm / 3 days</span>${w.elevation != null ? `<span>${ms('landscape')} ${Math.round(w.elevation)} m</span>` : ''}`;
  } catch (e) {}
}
window.routeTo = (lat, lon, name) => { $('#rTo').value = /^-?[\d.]+, -?[\d.]+$/.test(name) ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : name; openTab('route'); if (!$('#rFrom').value) $('#rFrom').focus(); else $('#routeBtn').click(); map.closePopup(); };
window.routeFrom = (lat, lon, name) => { $('#rFrom').value = /^-?[\d.]+, -?[\d.]+$/.test(name) ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : name; openTab('route'); $('#rTo').focus(); map.closePopup(); };
window.reportHere = (lat, lon) => { openTab('report'); setReportLocation(lat, lon); map.closePopup(); };
window.nearbyHelp = async (lat, lon) => {
  map.closePopup(); exposureLayer.clearLayers(); toast('Finding hospitals, police and shelters within 8 km… (can take up to a minute)', '#1a73e8', 90000);
  try {
    const r = await api(`/api/nearby?lat=${lat}&lon=${lon}`);
    const col = {hospital: '#d93025', clinic: '#e52592', police: '#1a73e8', fire_station: '#e8710a', shelter: '#188038'};
    r.features.forEach(f => {
      const c = f.properties.category.split('=').pop();
      L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {radius: 7, color: '#fff', weight: 2, fillColor: col[c] || '#5f6368', fillOpacity: 1})
        .bindPopup(`<div class="pop"><h5>${esc(f.properties.name)}</h5><div class="addr">${esc(c.replace('_', ' '))} · ${f.properties.distance_km} km</div>${f.properties.phone ? '☎ ' + esc(f.properties.phone) : ''}
        <div class="row"><a class="ghost btn" target="_blank" href="https://www.google.com/maps/dir/?api=1&destination=${f.geometry.coordinates[1]},${f.geometry.coordinates[0]}">${ms('directions')}Navigate</a></div></div>`).addTo(exposureLayer);
    });
    if (r.features.length) map.flyToBounds(L.featureGroup(exposureLayer.getLayers()).getBounds().extend([lat, lon]).pad(.2), {duration: 1});
    toast(`${r.features.length} places found within 8 km`, '#188038');
  } catch (e) { toast(e.message); }
};

// ---------- tabs ----------
function openTab(name) {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('on', x.dataset.tab === name));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.id === 'tab-' + name));
}
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => openTab(b.dataset.tab));

// ---------- provider switch ----------
async function loadSettings() {
  const s = await api('/api/settings'); $('#provider').value = s.provider;
  $('#provider').title = `text: ${s.text} · vision: ${s.vision} · speech: ${s.speech}`;
  if (s.websocket === false) startPolling(); else connectWS();
  if (s.provider === 'groq' && s.ai_key === false) toast('AI is off: GROQ_API_KEY is not set on the server (see README → Deploy).', '#d93025', 15000);
}
$('#provider').onchange = async (e) => {
  const s = await post('/api/settings', {provider: e.target.value});
  toast(`Now using ${s.provider}: ${s.text}`, '#1a73e8');
};

// ---------- counters ----------
async function loadStats() {
  const s = await api('/api/stats');
  $('#counters').innerHTML = `<span>Active<b>${s.active}</b></span><span class="c-high">High risk<b>${s.high}</b></span>
  <span>Roads blocked<b>${s.blocked}</b></span><span>Subscribers<b>${s.subscribers}</b></span>
  <span class="c-safe">Safe<b>${s.safe}</b></span><span class="c-help">Need help<b>${s.help}</b></span><span>Teams<b>${s.teams}</b></span>`;
}

// ---------- voice input (Whisper) ----------
async function recordTo(btn, onDone) {
  if (btn._rec) { btn._rec.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const rec = new MediaRecorder(stream); const chunks = [];
    rec.ondataavailable = e => chunks.push(e.data);
    rec.onstop = () => { stream.getTracks().forEach(t => t.stop()); btn.classList.remove('rec'); btn._rec = null;
      onDone(new Blob(chunks, {type: rec.mimeType || 'audio/webm'})); };
    rec.start(); btn._rec = rec; btn.classList.add('rec');
  } catch (e) { toast('Microphone not available: ' + e.message); }
}
document.querySelectorAll('.mic').forEach(btn => btn.onclick = () => recordTo(btn, async (blob) => {
  const fd = new FormData(); fd.append('audio', blob, 'voice.webm');
  const ta = document.getElementById(btn.dataset.target); ta.value = '…transcribing';
  try { const r = await api('/api/transcribe', {method: 'POST', body: fd}); ta.value = r.text || r.error || ''; }
  catch (e) { ta.value = ''; toast(e.message); }
}));

// ---------- A. Ask the map ----------
document.querySelectorAll('#tab-ask .chip').forEach(c => c.onclick = () => { $('#askQ').value = c.textContent; $('#askBtn').click(); });
$('#askQ').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#askBtn').click(); } });
$('#askBtn').onclick = async () => {
  const q = $('#askQ').value.trim(); if (!q) return;
  const out = $('#askOut'); loading(out, 'AI is writing and running the map query…'); $('#askBtn').disabled = true;
  const b = map.getBounds();
  try {
    const r = await post('/api/ask', {question: q, bbox: [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()]});
    const color = LAYER_COLORS[state.layers.length % LAYER_COLORS.length];
    const layer = L.geoJSON(r.geojson, {
      style: {color, weight: 6, opacity: .9},
      pointToLayer: (f, ll) => L.circleMarker(ll, {radius: 7, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1}),
      onEachFeature: (f, l) => {
        if (f.geometry.type !== 'Point') { l.bindPopup(`<div class="pop"><h5>${esc(f.properties.name)}</h5><div class="addr">${esc(f.properties.category)}</div></div>`); return; }
        const [lo, la] = f.geometry.coordinates;
        l.bindPopup(`<div class="pop"><h5>${esc(f.properties.name)}</h5><div class="addr">${esc(f.properties.category)}</div>${f.properties.phone ? '☎ ' + esc(f.properties.phone) : ''}${placeActions(la, lo, f.properties.name)}</div>`);
        l.bindTooltip(f.properties.name);
      }
    }).addTo(map);
    if (r.count) map.flyToBounds(layer.getBounds().pad(0.2), {maxZoom: 15, duration: 1});
    state.layers.push({id: r.id, label: r.label, layer, color, data: r.geojson, count: r.count});
    renderLayers();
    const atts = r.attempts.map((a, i) => `<div class="att">${a.error ? '<span class="bad">✗</span>' : '<span class="ok">✓</span>'} Attempt ${i + 1}${a.fallback ? ' (safety fallback)' : ''}: ${a.error ? esc(a.error).slice(0, 140) : (a.count + ' results')}</div><pre class="code">${esc(a.query)}</pre>`).join('');
    const isUr = r.parsed && r.parsed.language === 'ur';
    const isDist = r.parsed && r.parsed.relation === 'distance';
    out.innerHTML = `<div class="box"><b>${isDist ? '📏 Distance' : r.count + ' results'}</b><p class="${isUr ? 'ur' : ''}">${esc(r.summary)}</p>
      <button class="ghost" onclick="speak(${jsq(r.summary)}, '${isUr ? 'ur-PK' : 'en-US'}')">${ms('volume_up')}Listen</button>
      ${r.attempts.length ? `<details><summary>AI query + self-healing log (${r.attempts.length} attempt${r.attempts.length > 1 ? 's' : ''})</summary>${atts}</details>` : ''}</div>`;
  } catch (e) { fail(out, e); }
  $('#askBtn').disabled = false;
};
function renderLayers() {
  $('#layers').innerHTML = state.layers.map((l, i) => `<div class="layer"><i style="background:${l.color}"></i><span>${esc(l.label)} (${l.count})</span>
    <button class="ghost" title="Zoom to" onclick="zoomLayer(${i})">${ms('zoom_in_map')}</button><button class="ghost" title="Show / hide" onclick="toggleLayer(${i})">${ms('visibility')}</button><button class="ghost" title="Download GeoJSON" onclick="exportLayer(${i})">${ms('download')}</button><button class="ghost" title="Remove" onclick="removeLayer(${i})">${ms('close')}</button></div>`).join('') || '<p class="hint">Results of your questions appear here as map layers.</p>';
}
window.zoomLayer = (i) => { try { map.flyToBounds(state.layers[i].layer.getBounds().pad(.2), {duration: 1}); } catch (e) {} };
window.toggleLayer = (i) => { const l = state.layers[i].layer; map.hasLayer(l) ? map.removeLayer(l) : l.addTo(map); };
window.removeLayer = (i) => { map.removeLayer(state.layers[i].layer); state.layers.splice(i, 1); renderLayers(); };
window.exportLayer = (i) => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(state.layers[i].data)], {type: 'application/geo+json'}));
  a.download = state.layers[i].label.replace(/\W+/g, '_') + '.geojson'; a.click();
};

// ---------- hazards ----------
const TYPE_ICON = {landslide: 'landslide', rockfall: 'landslide', debris_flow: 'waves', flood: 'flood', road_subsidence: 'add_road', wall_failure: 'fence', none: 'help'};
function hazardIcon(h) {
  const c = COLORS[h.risk_level] || COLORS.low;
  const s = h.risk_level === 'high' ? 34 : h.risk_level === 'medium' ? 30 : 26;
  return L.divIcon({className: '', iconSize: [s, s], iconAnchor: [s / 2, s * 1.25], popupAnchor: [0, -s],
    html: `<div class="pin ${h.risk_level}"><div class="dot" style="width:${s}px;height:${s}px;background:${c}"><span>${h.risk_score}</span></div><div class="ring"></div></div>`});
}
function upsertHazard(h) {
  state.hazards[h.id] = h;
  if (state.markers[h.id]) hazLayer.removeLayer(state.markers[h.id]);
  if (['Resolved', 'False report'].includes(h.status)) { delete state.markers[h.id]; }
  else {
    const m = L.marker([h.lat, h.lon], {icon: hazardIcon(h), riseOnHover: true, zIndexOffset: h.risk_score * 10}).addTo(hazLayer);
    m.bindTooltip(`<b style="text-transform:capitalize">${esc(h.hazard_type.replace(/_/g, ' '))}</b> · risk ${h.risk_score}${h.road_blocked ? ' · road blocked' : ''}`, {direction: 'top', offset: [0, -30]});
    m.on('click', () => showCard(h.id)); state.markers[h.id] = m;
  }
  renderList();
}
async function loadHazards() {
  const hs = await api('/api/hazards');
  hazLayer.clearLayers(); state.markers = {}; state.hazards = {};
  hs.forEach(upsertHazard);
}
function renderList() {
  const lv = $('#fLevel').value, tp = $('#fType').value;
  const hs = Object.values(state.hazards).filter(h => !['Resolved', 'False report'].includes(h.status))
    .filter(h => (!lv || h.risk_level === lv) && (!tp || h.hazard_type === tp)).sort((a, b) => b.risk_score - a.risk_score);
  $('#hzList').innerHTML = hs.map(h => `<div class="hz ${h.risk_level}" onclick="showCard(${h.id})"><div class="thumb">${h.photo ? `<img src="${esc(h.photo)}" loading="lazy">` : ms(TYPE_ICON[h.hazard_type] || 'warning')}
    <div style="flex:1;min-width:0"><div class="t"><span>#${h.id} ${esc(h.hazard_type.replace(/_/g, ' '))}</span><span class="badge b-${h.risk_level}">${h.risk_score}</span></div>
    <div class="hint">Severity ${h.severity}/5 · ${esc(h.status)} · ${h.report_count} report(s)${h.road_blocked ? ' · <b style="color:var(--high)">ROAD BLOCKED</b>' : ''}</div></div></div></div>`).join('') || '<p class="hint">No active hazards.</p>';
}
$('#fLevel').onchange = renderList; $('#fType').onchange = renderList;

window.showCard = async (id) => {
  const h = await api('/api/hazards/' + id); state.selected = h; state.hazards[id] = {...state.hazards[id], ...h};
  map.flyTo([h.lat, h.lon], Math.max(map.getZoom(), 14), {duration: 1});
  const b = h.risk_breakdown || {}; const ex = (h.exposure || {}).counts || {};
  const rain = h.rain_daily || {mm: [], days: []}; const maxR = Math.max(10, ...rain.mm);
  const teamOpts = state.teams.map(t => `<option value="${t.id}">${esc(t.name)} (${esc(t.type)}) · ${esc(t.status)}</option>`).join('');
  const asg = (h.assignments || []).map(a => `<div class="hint">🚑 ${esc(a.team)}: <b>${esc(a.status)}</b></div>`).join('');
  $('#card').classList.remove('hidden'); document.body.classList.add('card-open');
  $('#card').innerHTML = `<button class="close" onclick="closeCard()" title="Close">${ms('close')}</button>
  ${h.photo ? `<div class="hero"><img src="${esc(h.photo)}"></div>` : ''}
  <div class="body">
  <h3>${ms(TYPE_ICON[h.hazard_type] || 'warning')} #${h.id} ${esc(h.hazard_type.replace(/_/g, ' '))}</h3>
  <div><span class="badge b-${h.risk_level}">${h.risk_level.toUpperCase()} · ${h.risk_score}/100</span> <span class="hint">severity ${h.severity}/5 · confidence ${Math.round((h.confidence || 0) * 100)}% · ${h.report_count} report(s)</span></div>
  <div class="hint">${ms('location_on')} ${h.lat.toFixed(5)}, ${h.lon.toFixed(5)} · ${new Date(h.created_at * 1000).toLocaleString()}</div>
  ${h.road_blocked ? `<div class="box err"><b>${ms('block')} ROAD BLOCKED</b></div>` : ''}
  <p>${esc(h.summary_en)}</p><p class="ur">${esc(h.summary_ur)}</p>
  <button class="ghost" onclick="speak(state.selected.summary_ur,'ur-PK')">${ms('volume_up')}Urdu</button>
  <h4>Risk breakdown</h4>
  <div class="riskbar"><div style="width:${b.severity}%;background:#d93025"></div><div style="width:${b.rain}%;background:#4285f4"></div><div style="width:${b.slope}%;background:#f29900"></div><div style="width:${b.exposure}%;background:#a142f4"></div></div>
  <div class="legend"><span><i style="background:#d93025"></i>Severity ${b.severity}/40</span><span><i style="background:#4285f4"></i>Rain ${b.rain}/25</span><span><i style="background:#f29900"></i>Slope ${b.slope}/20</span><span><i style="background:#a142f4"></i>Exposure ${b.exposure}/15</span></div>
  <div class="kv"><div><small>Slope</small>${h.slope_deg ?? '-'}°</div><div><small>Rain next 72 h</small>${h.rain_72h ?? '-'} mm</div>
  <div><small>Schools / colleges (1 km)</small>${ex.schools ?? '-'}</div><div><small>Health facilities (1 km)</small>${ex.health ?? '-'}</div>
  <div><small>Mosques (1 km)</small>${ex.worship ?? '-'}</div><div><small>Bridges (1 km)</small>${ex.bridges ?? '-'}</div></div>
  <div class="rain">${rain.mm.map((v, i) => `<div style="height:${Math.max(4, v / maxR * 85)}%"><span>${Math.round(v)} mm</span></div>`).join('')}</div>
  <div class="legend">${rain.days.map(d => `<span style="flex:1;text-align:center">${d.slice(5)}</span>`).join('')}</div>
  <h4>Geology evidence</h4><div class="chips">${(h.indicators || []).map(i => `<span class="chip">${esc(i)}</span>`).join('')}</div><p>${esc(h.evidence)}</p>
  <p><b>Action:</b> ${esc(h.recommended_action)}</p>
  ${h.transcript ? `<details><summary>Reporter's voice note / text</summary><p>${esc(h.transcript)}</p>${h.audio ? `<audio controls src="${esc(h.audio)}" style="width:100%"></audio>` : ''}</details>` : ''}
  <h4>Status & response</h4>
  <select onchange="setStatus(${h.id}, this.value)">${['New', 'Verified', 'Action taken', 'Resolved', 'False report'].map(s => `<option ${s === h.status ? 'selected' : ''}>${s}</option>`).join('')}</select>
  ${asg}
  <div class="inrow"><select id="assignTeam">${teamOpts || '<option value="">Add a team in Ops first</option>'}</select><button class="ghost" style="flex:0 0 90px" onclick="assign(${h.id})">${ms('assignment_ind')}Assign</button></div>
  <div class="actions">
    <button class="ghost" onclick="showExposure(${h.id})">${ms('radar')}Exposure map</button>
    <button class="ghost" onclick="genAlert(${h.id})">${ms('campaign')}Alert text</button>
    <a class="ghost btn" target="_blank" href="/print/letter/${h.id}?authority=National%20Highway%20Authority%20(NHA)">${ms('mail')}Letter to NHA</a>
    <a class="ghost btn" target="_blank" href="/print/letter/${h.id}?authority=Deputy%20Commissioner&lang=Urdu">${ms('mail')}اردو درخواست DC</a>
    <button class="ghost" onclick="notifyNow(${h.id})">${ms('notifications_active')}Notify nearby</button>
    <button class="ghost" onclick="askAbout(${h.id})">${ms('forum')}Safety advice</button>
    <button class="ghost" onclick="nearbyHelp(${h.lat},${h.lon})">${ms('local_hospital')}Nearby help</button>
    <a class="ghost btn" target="_blank" href="https://www.google.com/maps/dir/?api=1&destination=${h.lat},${h.lon}">${ms('directions')}Navigate</a>
  </div>
  <div id="alertOut"></div></div>`;
};
window.closeCard = () => { $('#card').classList.add('hidden'); document.body.classList.remove('card-open'); };
window.setStatus = async (id, status) => { const h = await api('/api/hazards/' + id, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({status})}); upsertHazard(h); loadStats(); toast(`Hazard #${id}: ${status}`, '#1a73e8'); };
window.assign = async (id) => {
  const tid = $('#assignTeam').value; if (!tid) return toast('Add a team in the Ops tab first');
  try { const r = await post('/api/assign', {hazard_id: id, team_id: +tid}); toast(r.telegram_sent ? 'Team notified on Telegram' : 'Team assigned (no Telegram chat id for this team)', '#188038'); loadTeams(); showCard(id); }
  catch (e) { toast(e.message); }
};
window.notifyNow = async (id) => { await post(`/api/hazards/${id}/notify`, {}); toast('Subscribers and families nearby notified', '#188038'); };
window.askAbout = (id) => { openTab('assist'); $('#asQ').value = 'What should people near this hazard do right now?'; $('#asBtn').click(); };
window.showExposure = async (id) => {
  const h = state.hazards[id]; exposureLayer.clearLayers();
  L.circle([h.lat, h.lon], {radius: 1000, color: '#a142f4', weight: 1.5, fillOpacity: .07, dashArray: '4 4'}).addTo(exposureLayer);
  map.flyToBounds(L.latLng(h.lat, h.lon).toBounds(2400), {duration: 1});
  toast('Loading schools, health facilities, mosques and bridges within 1 km…', '#1a73e8', 90000);
  try {
    const r = await api(`/api/hazards/${id}/exposure?r=1000`);
    L.geoJSON(r.geojson, {pointToLayer: (f, ll) => L.circleMarker(ll, {radius: 7, color: '#fff', weight: 2, fillColor: '#a142f4', fillOpacity: 1}),
      onEachFeature: (f, l) => l.bindPopup(`<b>${esc(f.properties.name)}</b><br>${esc(f.properties.category)}`).bindTooltip(f.properties.name)}).addTo(exposureLayer);
    toast(`${r.geojson.features.length} exposed facilities within 1 km`, '#188038');
  } catch (e) { toast(e.message); }
};
window.genAlert = async (id) => {
  const out = $('#alertOut'); loading(out, 'Writing bilingual alert…');
  try {
    const a = await post(`/api/alert/${id}`, {});
    out.innerHTML = `<div class="box"><b>SMS / WhatsApp</b><p>${esc(a.sms_en)}</p><p class="ur">${esc(a.sms_ur)}</p>
    <div class="inrow"><button class="ghost" onclick="navigator.clipboard.writeText(${jsq(a.sms_en + '\n\n' + a.sms_ur)});toast('Copied','#1a73e8')">${ms('content_copy')}Copy</button>
    <button class="ghost" onclick="speak(${jsq(a.sms_ur)},'ur-PK')">${ms('volume_up')}Urdu</button>
    <a class="ghost btn" target="_blank" href="https://wa.me/?text=${encodeURIComponent(a.sms_en + '\n\n' + a.sms_ur)}">${ms('share')}WhatsApp</a></div>
    <details><summary>Public notice</summary><p>${esc(a.notice_en)}</p><p class="ur">${esc(a.notice_ur)}</p></details></div>`;
  } catch (e) { fail(out, e); }
};

// ---------- B. report ----------
let repAudio = null;
function setReportLocation(lat, lon) {
  state.repLoc = {lat, lon};
  if (pickMarker) pickMarker.remove();
  pickMarker = L.marker([lat, lon], {icon: placeIcon(), draggable: true}).addTo(map).bindTooltip('Hazard location (drag to adjust)');
  pickMarker.on('dragend', () => { const p = pickMarker.getLatLng(); state.repLoc = {lat: p.lat, lon: p.lng}; $('#repLoc').textContent = `📍 ${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}`; });
  $('#repLoc').textContent = `📍 ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  if (!map.getBounds().contains([lat, lon])) map.flyTo([lat, lon], Math.max(map.getZoom(), 12), {duration: 1});
}
function setPhoto(file) {
  if (!file) return;
  if ($('#repImg').files[0] !== file) { const dt = new DataTransfer(); dt.items.add(file); $('#repImg').files = dt.files; }
  $('#repPrev').src = URL.createObjectURL(file); $('#repPrev').hidden = false; $('#dropText').textContent = file.name;
}
$('#repImg').onchange = (e) => setPhoto(e.target.files[0]);
const dz = $('#dropZone');
['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('over'); }));
['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('over'); }));
dz.addEventListener('drop', (e) => { const f = e.dataTransfer.files[0]; if (f && f.type.startsWith('image/')) setPhoto(f); });
$('#recBtn').onclick = () => recordTo($('#recBtn'), (blob) => { repAudio = blob; $('#recState').textContent = `✓ voice note (${Math.round(blob.size / 1024)} KB)`; });
$('#pickLoc').onclick = () => { state.pickMode = true; map.getContainer().style.cursor = 'crosshair'; toast('Click the hazard location on the map', '#1a73e8'); };
$('#gpsLoc').onclick = () => locate().then(p => setReportLocation(p.lat, p.lon)).catch(e => toast(e.message));
$('#repBtn').onclick = async () => {
  const fd = new FormData(); const img = $('#repImg').files[0];
  if (img) fd.append('image', img);
  if (repAudio) fd.append('audio', repAudio, 'voice.webm');
  fd.append('description', $('#repDesc').value);
  if (state.repLoc) { fd.append('lat', state.repLoc.lat); fd.append('lon', state.repLoc.lon); }
  fd.append('source', 'dashboard');
  const out = $('#repOut'); loading(out, 'Transcribing, analysing photo with the geology checklist, checking rain, slope and exposure…');
  $('#repBtn').disabled = true;
  try {
    const h = await api('/api/report', {method: 'POST', body: fd});
    out.innerHTML = `<div class="box">✓ ${h.merged ? 'Merged with existing hazard' : 'Hazard created'} #${h.id} · <span class="badge b-${h.risk_level}">${h.risk_score}</span></div>`;
    upsertHazard(h); showCard(h.id); repAudio = null; $('#recState').textContent = 'optional';
    if (pickMarker) { pickMarker.remove(); pickMarker = null; }
    $('#repImg').value = ''; $('#repPrev').hidden = true; $('#dropText').textContent = 'Choose or drop a photo'; $('#repDesc').value = ''; state.repLoc = null;
    $('#repLoc').textContent = 'Not set (photo GPS is used if present)';
  } catch (e) { fail(out, e); }
  $('#repBtn').disabled = false;
};

// ---------- E. route ----------
acAttach($('#rFrom'), $('#rFrom').nextElementSibling, (p) => { $('#rFrom').value = p.icon === 'my_location' ? `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}` : p.name; });
acAttach($('#rTo'), $('#rTo').nextElementSibling, (p) => { $('#rTo').value = p.icon === 'my_location' ? `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}` : p.name; });
$('#rSwap').onclick = () => { const a = $('#rFrom').value; $('#rFrom').value = $('#rTo').value; $('#rTo').value = a; };
$('#rMe').onclick = () => locate(false).then(p => { $('#rFrom').value = `${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`; toast('Starting from your location', '#1a73e8'); }).catch(e => toast(e.message));
const STEP_ICON = (s) => s.type === 'arrive' ? 'flag' : s.type === 'depart' ? 'trip_origin' : /roundabout|rotary/.test(s.type) ? 'roundabout_right'
  : /sharp left|left/.test(s.modifier) ? 'turn_left' : /sharp right|right/.test(s.modifier) ? 'turn_right' : s.modifier === 'uturn' ? 'u_turn_left' : 'straight';
$('#routeBtn').onclick = async () => {
  const from = $('#rFrom').value.trim(), to = $('#rTo').value.trim(); if (!from || !to) return toast('Enter a start and a destination');
  const out = $('#routeOut'); loading(out, 'Routing, scanning hazards along the road, checking rain…'); $('#routeBtn').disabled = true;
  routeLayer.clearLayers();
  try {
    const r = await post('/api/route-check', {origin: from, destination: to});
    const vcol = {safe: '#1a73e8', caution: '#f29900', avoid: '#d93025'}[r.verdict];
    if (r.alternate) {
      L.geoJSON(r.alternate.geojson, {style: {color: '#fff', weight: 9, opacity: .9}}).addTo(routeLayer);
      L.geoJSON(r.alternate.geojson, {style: {color: '#188038', weight: 6, dashArray: '10 8'}}).addTo(routeLayer).bindTooltip('Safer alternate route', {sticky: true});
    }
    L.geoJSON(r.primary.geojson, {style: {color: '#ffffff', weight: 10, opacity: .95}}).addTo(routeLayer);
    const pl = L.geoJSON(r.primary.geojson, {style: {color: vcol, weight: 6, opacity: .95}}).addTo(routeLayer);
    r.help_points.features.forEach(f => {
      const c = f.properties.category.split('=').pop(); const col = {hospital: '#d93025', police: '#1a73e8', fuel: '#f9ab00'}[c] || '#5f6368';
      L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {radius: 5, color: '#fff', weight: 1.5, fillColor: col, fillOpacity: 1})
        .bindPopup(`<b>${esc(f.properties.name)}</b><br>${c} · km ${f.properties.km_along}${f.properties.phone ? '<br>☎ ' + esc(f.properties.phone) : ''}`).addTo(routeLayer);
    });
    L.circleMarker([r.origin.lat, r.origin.lon], {radius: 7, color: '#202124', weight: 3, fillColor: '#fff', fillOpacity: 1}).bindTooltip(r.origin.name).addTo(routeLayer);
    L.marker([r.destination.lat, r.destination.lon], {icon: placeIcon()}).bindTooltip(r.destination.name).addTo(routeLayer);
    map.flyToBounds(pl.getBounds().pad(0.1), {duration: 1});
    const hz = r.primary.hazards.map(x => `<div class="hz ${x.risk_level}" onclick="showCard(${x.id})"><div class="t"><span>km ${x.km_from_start} · ${esc(x.type.replace(/_/g, ' '))}</span><span class="badge b-${x.risk_level}">${x.risk_score}</span></div>${x.road_blocked ? '<div class="hint" style="color:var(--high)">Road blocked</div>' : ''}</div>`).join('');
    const counts = {hospital: 0, police: 0, fuel: 0}; r.help_points.features.forEach(f => { const c = f.properties.category.split('=').pop(); if (c in counts) counts[c]++; });
    const steps = (r.alternate || r.primary).steps || [];
    out.innerHTML = `<div class="verdict v-${r.verdict}">${{safe: '🟢 SAFE TO TRAVEL', caution: '🟠 TRAVEL WITH CAUTION', avoid: '🔴 AVOID / DELAY'}[r.verdict]}</div>
      <div class="stats"><div><b>${fmtH(r.primary.duration_h)}</b><small>driving time</small></div><div><b>${r.primary.distance_km} km</b><small>distance</small></div><div><b>${r.max_rain_mm} mm</b><small>max rain, 72 h</small></div><div><b>${r.primary.hazards.length}</b><small>hazards</small></div></div>
      ${r.alternate ? `<div class="box" style="border-color:#ceead6;background:#e6f4ea"><b>${ms('alt_route')} Safer alternate route:</b> ${r.alternate.distance_km} km · ${fmtH(r.alternate.duration_h)} · ${r.alternate.hazards.length} hazards (green dashed line)</div>` : ''}
      <div class="box"><p style="margin-top:0">${esc(r.advice.en)}</p><p class="ur">${esc(r.advice.ur)}</p>
      <div class="inrow"><button class="ghost" onclick="speak(${jsq(r.advice.ur || '')},'ur-PK')">${ms('volume_up')}Urdu</button>
      <a class="ghost btn" target="_blank" href="/print/card?origin=${encodeURIComponent(from)}&destination=${encodeURIComponent(to)}">${ms('badge')}Emergency card</a>
      <a class="ghost btn" target="_blank" href="https://www.google.com/maps/dir/?api=1&origin=${r.origin.lat},${r.origin.lon}&destination=${r.destination.lat},${r.destination.lon}">${ms('navigation')}Navigate</a></div></div>
      <h4>Hazards on route (${r.primary.hazards.length})</h4>${hz || '<p class="hint">None reported within 500 m of the road.</p>'}
      <h4>Help along the route</h4><p class="hint">${r.help_points.unavailable ? 'OpenStreetMap servers are busy, so hospitals / police / fuel could not be loaded. Check the route again in a minute.' : `🏥 ${counts.hospital} hospitals · 👮 ${counts.police} police · ⛽ ${counts.fuel} fuel stations`}</p>
      ${steps.length ? `<h4>Directions${r.alternate ? ' (alternate route)' : ''}</h4><ul class="steps">${steps.map(s => `<li onclick="map.flyTo([${s.lat},${s.lon}],15,{duration:1})">${ms(STEP_ICON(s))}<span>${esc(s.text)}</span><small>${s.km ? fmtKm(s.km) : ''}</small></li>`).join('')}</ul>` : ''}`;
  } catch (e) { fail(out, e); }
  $('#routeBtn').disabled = false;
};

// ---------- ops ----------
async function loadTeams() {
  state.teams = await api('/api/teams');
  $('#teams').innerHTML = state.teams.map(t => `<div class="layer"><i style="background:${t.status === 'busy' ? '#f29900' : '#188038'}"></i><span>${esc(t.name)} · <span class="hint">${esc(t.type)}</span></span><span class="badge b-${t.status === 'busy' ? 'medium' : 'low'}">${esc(t.status)}</span></div>`).join('') || '<p class="hint">No teams yet.</p>';
}
$('#tAdd').onclick = async () => {
  if (!$('#tName').value) return toast('Enter a team name');
  await post('/api/teams', {name: $('#tName').value, type: $('#tType').value, chat_id: $('#tChat').value});
  $('#tName').value = $('#tChat').value = ''; loadTeams(); loadStats(); toast('Team added', '#188038');
};

// ---------- assistant ----------
document.querySelectorAll('#tab-assist .chip').forEach(c => c.onclick = () => { $('#asQ').value = c.textContent; $('#asBtn').click(); });
$('#asQ').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#asBtn').click(); } });
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/^#+\s*(.+)$/gm, '<b>$1</b>').replace(/^\s*[-*]\s+/gm, '• ');
$('#asBtn').onclick = async () => {
  const q = $('#asQ').value.trim(); if (!q) return; const out = $('#asOut'); loading(out, 'Thinking…'); $('#asBtn').disabled = true;
  try {
    const r = await post('/api/assistant', {question: q, hazard_id: state.selected ? state.selected.id : null});
    const ur = /[؀-ۿ]/.test(r.answer);
    out.innerHTML = `<div class="box"><p class="${ur ? 'ur' : ''}" style="white-space:pre-wrap;margin-top:0">${md(r.answer)}</p><button class="ghost" onclick="speak(${jsq(r.answer.replace(/[*#|]/g, ''))},'${ur ? 'ur-PK' : 'en-US'}')">${ms('volume_up')}Listen</button></div>`;
  } catch (e) { fail(out, e); }
  $('#asBtn').disabled = false;
};

// ---------- live updates ----------
function connectWS() {
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onopen = () => $('#live').classList.add('on');
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === 'hazard') {
      const isNew = !state.hazards[m.data.id];
      upsertHazard(m.data); loadStats();
      if (isNew) { beep(); toast(`New ${m.data.risk_level.toUpperCase()} risk ${m.data.hazard_type.replace(/_/g, ' ')} reported (${m.data.risk_score})`, COLORS[m.data.risk_level]);
        feed(`New hazard #${m.data.id} · ${esc(m.data.hazard_type)} · risk ${m.data.risk_score} · via ${esc(m.data.source)}`); }
      else feed(`Hazard #${m.data.id} updated: ${esc(m.data.status)}${m.data.merged ? ' (another report merged)' : ''}`);
      if (state.selected && state.selected.id === m.data.id && !$('#card').classList.contains('hidden')) showCard(m.data.id);
    } else if (m.type === 'checkin') {
      feed(`${m.data.status === 'safe' ? '✅' : '🆘'} ${esc(m.data.name || 'Someone')} checked in: ${esc(m.data.status)}`); loadStats();
      if (m.data.status === 'help' && m.data.lat) { toast(`🆘 ${m.data.name || 'Someone'} needs help`); L.circleMarker([m.data.lat, m.data.lon], {radius: 9, color: '#fff', fillColor: '#d93025', fillOpacity: 1}).bindPopup('🆘 Help request').addTo(hazLayer); }
    } else if (m.type === 'notified') feed(`📲 Alert sent to ${m.data.subscribers} subscriber(s) near hazard #${m.data.hazard_id}`);
  };
  let opened = false;
  ws.addEventListener('open', () => { opened = true; wsFails = 0; });
  ws.onclose = () => {
    $('#live').classList.remove('on');
    if (!opened && ++wsFails >= 3) return startPolling();  // host without WebSockets: refresh instead
    setTimeout(connectWS, 2000);
  };
}
let wsFails = 0, polling = null;
function startPolling() {
  if (polling) return;
  $('#live').classList.add('on'); $('#live').lastChild.textContent = 'Auto-refresh'; $('#live').title = 'Refreshes every 20 seconds';
  polling = setInterval(async () => {
    try {
      const hs = await api('/api/hazards'); const ids = new Set(hs.map(h => h.id));
      hs.forEach(h => { const old = state.hazards[h.id]; if (!old) { feed(`New hazard #${h.id} · ${esc(h.hazard_type)} · risk ${h.risk_score}`); beep(); }
        if (!old || old.updated_at !== h.updated_at) upsertHazard(h); });
      Object.keys(state.hazards).filter(id => !ids.has(+id)).forEach(id => upsertHazard({...state.hazards[id], status: 'Resolved'}));
      loadStats();
    } catch (e) {}
  }, 20000);
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { if (measuring) measureStop(); else closeCard(); }
  if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $('#mq').focus(); }
});

loadSettings(); loadStats(); loadHazards(); loadTeams(); renderLayers();
