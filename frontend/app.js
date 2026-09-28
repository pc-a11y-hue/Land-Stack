'use strict';
/* Land Stack front-end. Plain JS, no build step.
   SECURITY: every value that came from the server or a user is passed through esc() before it goes into
   innerHTML. Never concatenate raw data into markup. */

// ---- Map tiles -------------------------------------------------------------------------------
// Default is OpenStreetMap. OSM draws disputed borders (e.g. J&K) using a neutral international
// convention. To use an India-compliant provider (Bhuvan, Mappls, …) change ONLY this object — you
// need your own API key from that provider. Nothing else in the app depends on the tile source.
const MAP_TILES = { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: '&copy; OpenStreetMap contributors', maxZoom: 19 };

const ZONE_COLORS = { A: '#4caf50', C: '#f59e0b', U: '#2f80ed', R: '#8d6e63' };
const ZONE_NAMES = { A: 'Agriculture', C: 'Commercial', U: 'Urban', R: 'Rural' };
const BUILD_COLORS = { 'Approved': '#3fb37f', 'Pending': '#f59e0b', 'Not Applicable': '#b0b8c1' };
const DEED_STEPS = [['DRAFT', 'Drafted'], ['AUTHENTICATED', 'OTP verified'], ['PAID', 'Fees paid'], ['REGISTERED', 'Registered'], ['MUTATED', 'Mutated']];

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const inr = n => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const when = s => s ? esc(String(s).replace('T', ' ').replace('Z', ' UTC').slice(0, 20)) : '—';
const debounce = (fn, ms) => { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; };

const S = {
  me: { logged_in: false }, tab: 'map', geo: null, polys: {}, selected: null, lastDetail: null,
  demo: null, demoOtps: {}, regions: [], region: 'all', picks: {}, regDraw: { pts: [] }, regValid: false,
  expectedArea: null, deferredInstall: null
};
const isOfficer = () => S.me.logged_in && S.me.role !== 'citizen';
const isCitizen = () => S.me.logged_in && S.me.role === 'citizen';
const role = () => (S.me.logged_in ? S.me.role : null);

// ---- helpers ---------------------------------------------------------------------------------
async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {}, credentials: 'same-origin' };
  if (init.method !== 'GET') {
    init.headers['Content-Type'] = 'application/json';
    init.headers['X-Requested-With'] = 'LandStack';        // CSRF guard the server requires on writes
    init.body = JSON.stringify(opts.body || {});
  }
  try {
    const r = await fetch(path, init);
    let data = null;
    try { data = await r.json(); } catch (e) { /* non-JSON */ }
    return { ok: r.ok, status: r.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { error: 'Network error — check your connection.' } };
  }
}
const post = (path, body) => api(path, { method: 'POST', body });
const errText = r => esc((r.data && r.data.error) || `Request failed (${r.status})`);

let toastTimer;
function toast(msg, ms = 3200) {
  const el = $('toast'); el.textContent = msg; el.classList.remove('hidden');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.add('hidden'), ms);
}
function openModal(html) {
  closeModal();
  const o = document.createElement('div'); o.className = 'overlay'; o.id = 'overlay';
  o.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  o.addEventListener('mousedown', e => { if (e.target === o) closeModal(); });
  $('modalRoot').appendChild(o);
  const first = o.querySelector('input,select,button'); if (first) first.focus();
  return o;
}
const closeModal = () => { $('modalRoot').innerHTML = ''; };
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// Reusable "find a person" picker (registration officers use it for owners, buyers, heirs).
function personPicker(inputId, resultsId, pickedId, key, onPick) {
  const input = $(inputId), results = $(resultsId), picked = $(pickedId);
  const run = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) { results.innerHTML = ''; return; }
    const r = await api('/api/persons/lookup?q=' + encodeURIComponent(q));
    if (!r.ok) { results.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
    results.innerHTML = r.data.length ? r.data.map(p => `<button type="button" class="btn small" style="margin:0 6px 6px 0" data-pid="${esc(p.person_id)}">${esc(p.name)} · <span class="mono">${esc(p.person_id)}</span> · ${esc(p.mobile)} · ${p.parcels} plot(s)</button>`).join('') : '<span class="muted small">No match</span>';
    results.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
      const p = r.data.find(x => x.person_id === b.dataset.pid);
      S.picks[key] = p; results.innerHTML = ''; input.value = '';
      picked.classList.remove('hidden'); picked.innerHTML = `Selected: <b>${esc(p.name)}</b> <span class="mono">${esc(p.person_id)}</span> · ${esc(p.mobile)}`;
      if (onPick) onPick(p);
    }));
  }, 300);
  input.addEventListener('input', run);
}

// ---- authentication -------------------------------------------------------------------------
async function loadDemo() {
  if (S.demo !== null) return S.demo;
  const r = await api('/api/demo/logins');
  S.demo = r.ok ? r.data : false;
  return S.demo;
}
function openLoginChooser() {
  openModal(`<h2>${esc(t('login'))}</h2><div class="row"><button class="btn blue" id="chooseCit">${esc(t('citizen_login'))}</button><button class="btn blue" id="chooseOff">${esc(t('officer_login'))}</button></div>`);
  $('chooseCit').onclick = () => openLogin('citizen'); $('chooseOff').onclick = () => openLogin('officer');
}
async function openLogin(kind) {
  const demo = await loadDemo();
  let demoHtml = '';
  if (demo) {
    if (kind === 'officer') {
      demoHtml = `<label class="f"><span>${esc(t('demo_accounts'))}</span><select id="demoSel"><option value="">${esc(t('choose'))}</option>${demo.officers.map(o => `<option value="${esc(o.username)}|${esc(o.password)}">${esc(o.display_name)} — ${esc(o.username)}</option>`).join('')}</select></label>`;
    } else {
      const groups = {};
      demo.citizens.forEach(c => { (groups[c.district] = groups[c.district] || []).push(c); });
      demoHtml = `<label class="f"><span>${esc(t('demo_accounts'))}</span><select id="demoSel"><option value="">${esc(t('choose'))}</option>${Object.keys(groups).sort().map(d => `<optgroup label="${esc(d)}">${groups[d].map(c => `<option value="${esc(c.username)}|${esc(c.password)}">${esc(c.name)} — ${esc(c.username)}</option>`).join('')}</optgroup>`).join('')}</select></label>`;
    }
  }
  const o = openModal(`<h2>${esc(t(kind === 'officer' ? 'officer_login' : 'citizen_login'))}</h2>
    <div id="loginErr"></div>${demoHtml}
    <label class="f"><span>${esc(t('username'))}</span><input id="lgUser" autocomplete="username"></label>
    <label class="f"><span>${esc(t('password'))}</span><input id="lgPass" type="password" autocomplete="current-password"></label>
    <div class="row"><button class="btn blue" id="lgGo">${esc(t('continue'))}</button><button class="btn" id="lgCancel">${esc(t('cancel'))}</button></div>`);
  const sel = $('demoSel');
  if (sel) sel.onchange = () => { const [u, p] = sel.value.split('|'); $('lgUser').value = u || ''; $('lgPass').value = p || ''; };
  $('lgCancel').onclick = closeModal;
  const go = async () => {
    const body = { username: $('lgUser').value.trim(), password: $('lgPass').value };
    $('lgGo').disabled = true;
    if (kind === 'officer') {
      const r = await post('/api/login/officer', body);
      if (!r.ok) { $('loginErr').innerHTML = `<div class="banner err">${errText(r)}</div>`; $('lgGo').disabled = false; return; }
      closeModal(); await afterAuthChange();
    } else {
      const r = await post('/api/login/citizen', body);
      if (!r.ok) { $('loginErr').innerHTML = `<div class="banner err">${errText(r)}</div>`; $('lgGo').disabled = false; return; }
      showOtpStep(r.data);
    }
  };
  $('lgGo').onclick = go;
  o.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
}
function showOtpStep(ch) {
  openModal(`<h2>${esc(t('otp'))}</h2>
    <p class="muted small">A 6-digit code was sent to ${esc(ch.mobile_masked)}.</p>
    ${ch.demo_otp ? `<div class="sms">📱 ${esc(t('demo_otp'))}: <b>${esc(ch.demo_otp)}</b><br><span class="small">${esc(ch.demo_note)}</span></div>` : ''}
    <div id="otpErr"></div>
    <label class="f"><span>${esc(t('otp'))}</span><input id="otpIn" inputmode="numeric" maxlength="6" autocomplete="one-time-code" value="${esc(ch.demo_otp || '')}"></label>
    <div class="row"><button class="btn blue" id="otpGo">${esc(t('verify'))}</button><button class="btn" id="otpCancel">${esc(t('cancel'))}</button></div>`);
  $('otpCancel').onclick = closeModal;
  const go = async () => {
    const r = await post('/api/login/citizen/verify', { challenge_id: ch.challenge_id, otp: $('otpIn').value.trim() });
    if (!r.ok) { $('otpErr').innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
    closeModal(); await afterAuthChange();
  };
  $('otpGo').onclick = go; $('otpIn').addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
}
async function refreshMe() {
  const r = await api('/api/me'); S.me = r.ok ? r.data : { logged_in: false };
}
async function afterAuthChange() {
  await refreshMe();
  S.selected = null; S.lastDetail = null; S.demoOtps = {}; S.picks = {};
  $('detailPanel').innerHTML = `<p class="muted">${esc(t('select_plot'))}</p>`;
  renderHeader(); buildTabs();
  await loadParcels();
  if (S.me.logged_in) {
    if (S.me.role !== 'citizen' && S.me.region) { S.region = S.me.region; $('regionSel').value = S.region; }
    else if (S.me.role === 'citizen' && S.me.owned_ulpins.length) {
      const f = S.geo.features.find(x => x.properties.ulpin === S.me.owned_ulpins[0]);
      if (f) { S.region = f.properties.context; $('regionSel').value = S.region; }
    }
  }
  showTab('map'); fitRegion();
}
async function doLogout() {
  await post('/api/logout'); S.me = { logged_in: false };
  await afterAuthChange(); toast('Logged out');
}
function renderHeader() {
  const chip = $('userChip');
  if (S.me.logged_in) {
    chip.classList.remove('hidden');
    chip.textContent = S.me.role === 'citizen' ? `${S.me.display_name} · ${S.me.person_id}` : S.me.display_name;
    $('loginBtn').classList.add('hidden'); $('logoutBtn').classList.remove('hidden');
  } else { chip.classList.add('hidden'); $('loginBtn').classList.remove('hidden'); $('logoutBtn').classList.add('hidden'); }
}

// ---- tabs ----------------------------------------------------------------------------------
const TABS = [
  { id: 'map', key: 'tab_map', show: () => true },
  { id: 'search', key: 'tab_search', show: () => true },
  { id: 'myland', key: 'tab_myland', show: isCitizen },
  { id: 'txn', key: 'tab_txn', show: isCitizen },
  { id: 'updates', key: 'tab_updates', show: () => isCitizen() || isOfficer() },
  { id: 'register', key: 'tab_register', show: () => role() === 'registration_officer' },
  { id: 'deeds', key: 'tab_deeds', show: isOfficer },
  { id: 'requests', key: 'tab_requests', show: isOfficer },
  { id: 'risk', key: 'tab_risk', show: isOfficer },
  { id: 'satellite', key: 'tab_satellite', show: isOfficer },
  { id: 'reports', key: 'tab_reports', show: isOfficer },
  { id: 'audit', key: 'tab_audit', show: isOfficer }
];
function buildTabs() {
  const nav = $('tabs'); nav.innerHTML = '';
  TABS.filter(x => x.show()).forEach(x => {
    const b = document.createElement('button'); b.type = 'button'; b.dataset.tab = x.id; b.setAttribute('role', 'tab');
    b.textContent = t(x.key); b.onclick = () => showTab(x.id); nav.appendChild(b);
  });
  if (!TABS.find(x => x.id === S.tab && x.show())) S.tab = 'map';
}
const LOADERS = {
  map: () => { setTimeout(() => { S.map.invalidateSize(); }, 50); },
  myland: loadMyLand, txn: loadTransactions, updates: loadUpdates, register: initRegister, deeds: loadDeeds,
  requests: loadRequests, risk: loadRisk, satellite: loadSatellite, reports: loadReports, audit: loadAudit
};
function showTab(id) {
  if (!TABS.find(x => x.id === id && x.show())) id = 'map';
  S.tab = id;
  document.querySelectorAll('.tab').forEach(s => s.classList.toggle('active', s.id === 'tab-' + id));
  document.querySelectorAll('#tabs button').forEach(b => { const on = b.dataset.tab === id; b.classList.toggle('active', on); b.setAttribute('aria-selected', on); });
  if (LOADERS[id]) LOADERS[id]();
}

// ---- map & layers ---------------------------------------------------------------------------
function initMap() {
  S.map = L.map('map', { zoomControl: true }).setView([22.5, 79], 5);
  L.tileLayer(MAP_TILES.url, { attribution: MAP_TILES.attribution, maxZoom: MAP_TILES.maxZoom }).addTo(S.map);
  S.polyGroup = L.layerGroup().addTo(S.map); S.labelGroup = L.layerGroup().addTo(S.map); S.utilGroup = L.layerGroup().addTo(S.map);
  S.map.on('zoomend', updateLabelVisibility);
}
const layerState = () => ({
  bounds: $('lyBounds').checked, labels: $('lyLabels').checked,
  colorBy: document.querySelector('input[name=colorBy]:checked').value,
  tax: $('lyTax').checked, sat: $('lySat').checked, util: $('lyUtil').checked
});
function styleFor(p, selected) {
  const s = layerState();
  let fill = ZONE_COLORS[p.zone_code] || '#999', fo = 0.45;
  if (s.colorBy === 'encumbrance') { if (p.detail) fill = p.has_encumbrance ? '#e5484d' : '#3fb37f'; else { fill = '#c5ccd4'; fo = 0.35; } }
  else if (s.colorBy === 'building') { if (p.detail) fill = BUILD_COLORS[p.building_status] || '#b0b8c1'; else { fill = '#c5ccd4'; fo = 0.35; } }
  let stroke = '#3d4b5c', weight = 1.2, dash = null;
  if (p.is_mine) { stroke = '#e08a00'; weight = 3.5; }
  if (s.tax && p.detail) { stroke = p.tax_status === 'Due' ? '#c62828' : '#2e7d32'; weight = 3.5; }
  if (s.sat && p.detail && p.under_watch) { stroke = '#7b1fa2'; weight = 3.5; dash = '7 5'; }
  if (selected) { stroke = '#000'; weight = 4; }
  if (!s.bounds) return { color: stroke, weight: selected ? 4 : 0, opacity: selected ? 1 : 0, fillColor: fill, fillOpacity: 0.12 };
  return { color: stroke, weight, dashArray: dash, fillColor: fill, fillOpacity: fo };
}
function renderLegend() {
  const s = layerState(), rows = [];
  const sw = (c, txt) => `<div><i style="background:${c}"></i>${esc(txt)}</div>`;
  if (s.colorBy === 'zoning') Object.keys(ZONE_NAMES).forEach(z => rows.push(sw(ZONE_COLORS[z], `${z} · ${ZONE_NAMES[z]}`)));
  if (s.colorBy === 'encumbrance') rows.push(sw('#e5484d', 'Encumbered'), sw('#3fb37f', 'Clear'), sw('#c5ccd4', 'Detail restricted'));
  if (s.colorBy === 'building') Object.entries(BUILD_COLORS).forEach(([k, c]) => rows.push(sw(c, k)));
  if (s.tax) rows.push(`<div><i style="background:none;border:3px solid #c62828"></i>Tax due</div><div><i style="background:none;border:3px solid #2e7d32"></i>Tax paid</div>`);
  if (s.sat) rows.push(`<div><i style="background:none;border:3px dashed #7b1fa2"></i>Satellite watch</div>`);
  if (s.util) rows.push(`<div><span class="ugap">W✕ E✕</span> no water / power</div>`);
  if (isCitizen()) rows.push(`<div><i style="background:none;border:3px solid #e08a00"></i>${esc(t('my_plots'))}</div>`);
  $('legend').innerHTML = `<b>${esc(t('legend'))}</b>` + rows.join('');
}
function updateLabelVisibility() {
  const show = layerState().labels && S.map.getZoom() >= 15;
  if (show && !S.map.hasLayer(S.labelGroup)) S.map.addLayer(S.labelGroup);
  if (!show && S.map.hasLayer(S.labelGroup)) S.map.removeLayer(S.labelGroup);
}
async function loadParcels() {
  const r = await api('/api/parcels');
  if (!r.ok) { toast('Could not load parcels'); return; }
  S.geo = r.data; renderParcels();
}
function renderParcels() {
  if (!S.geo) return;
  S.polyGroup.clearLayers(); S.labelGroup.clearLayers(); S.utilGroup.clearLayers(); S.polys = {};
  const s = layerState();
  S.geo.features.forEach(f => {
    const p = f.properties, latlngs = f.geometry.coordinates[0].map(c => [c[1], c[0]]);
    const poly = L.polygon(latlngs, styleFor(p, p.ulpin === S.selected));
    poly.props = p;
    poly.bindTooltip(`${esc(p.ulpin)}<br>${p.owner_name ? esc(p.owner_name) : '<i>Private owner</i>'}`, { sticky: true });
    poly.on('click', () => selectParcel(p.ulpin, false));
    poly.addTo(S.polyGroup); S.polys[p.ulpin] = poly;
    const c = poly.getBounds().getCenter();
    L.marker(c, { icon: L.divIcon({ className: '', html: `<div class="zlabel" style="border-color:${ZONE_COLORS[p.zone_code] || '#333'}">${esc(p.zone_code)}</div>`, iconSize: [18, 18], iconAnchor: [9, 9] }) })
      .on('click', () => selectParcel(p.ulpin, false)).addTo(S.labelGroup);
    if (s.util && p.detail && (!p.water || !p.electricity)) {
      const txt = (!p.water ? 'W✕ ' : '') + (!p.electricity ? 'E✕' : '');
      L.marker(c, { interactive: false, icon: L.divIcon({ className: '', html: `<div class="ugap">${txt}</div>`, iconSize: [40, 16], iconAnchor: [20, -8] }) }).addTo(S.utilGroup);
    }
  });
  renderLegend(); updateLabelVisibility();
}
function restyleAll() {
  Object.values(S.polys).forEach(poly => poly.setStyle(styleFor(poly.props, poly.props.ulpin === S.selected)));
}
function fitRegion() {
  S.map.invalidateSize();
  const feats = ((S.geo && S.geo.features) || []).filter(f => S.region === 'all' || f.properties.context === S.region);
  if (!feats.length) { S.map.setView([22.5, 79], 5); return; }
  const b = L.latLngBounds(feats.flatMap(f => f.geometry.coordinates[0].map(c => [c[1], c[0]])));
  S.map.fitBounds(b.pad(0.1), { maxZoom: 18 });
}
async function loadRegions() {
  const r = await api('/api/regions'); S.regions = r.ok ? r.data : [];
  $('regionSel').innerHTML = '<option value="all">All regions</option>' + S.regions.map(x => `<option value="${esc(x.context)}">${esc(x.district)} — ${esc(x.label)}</option>`).join('');
}
function openOnMap(ulpin) {
  const f = S.geo && S.geo.features.find(x => x.properties.ulpin === ulpin);
  if (f) { S.region = f.properties.context; $('regionSel').value = S.region; }
  showTab('map');
  setTimeout(() => { S.map.invalidateSize(); selectParcel(ulpin, true); }, 120);
}
async function selectParcel(ulpin, fly = true) {
  S.selected = ulpin; restyleAll();
  const r = await api('/api/parcel/' + encodeURIComponent(ulpin));
  if (!r.ok) { $('detailPanel').innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  renderDossier(r.data);
  if (fly && S.polys[ulpin]) S.map.fitBounds(S.polys[ulpin].getBounds().pad(2), { maxZoom: 19 });
  if (window.innerWidth <= 900) $('detailPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---- dossier --------------------------------------------------------------------------------
const badge = (text, cls = '') => `<span class="badge ${cls}">${esc(text)}</span>`;
const sec = (title, inner) => `<div class="dsec"><h4>${title}</h4>${inner}</div>`;
const kv = rows => `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
const term = tm => `${esc(tm.en)}${tm.local ? ` <span class="local">${esc(tm.local)}</span>` : ''}`;

function renderDossier(d) {
  S.lastDetail = d;
  const box = $('detailPanel');
  if (d.restricted) {
    box.innerHTML = `<h3 class="mono">${esc(d.ulpin)}</h3><div>${badge(t('restricted'), 'amber')}${badge(d.district)}${badge(d.zone_code + ' · ' + (ZONE_NAMES[d.zone_code] || ''), 'blue')}</div>
      ${kv([[esc(t('owner')), d.owner_name ? esc(d.owner_name) : '<i>Private</i>'], [esc(t('survey_no')), esc(d.survey_number)]])}
      <div class="banner info" style="margin-top:10px">${esc(d.message)}</div>`;
    return;
  }
  const ror = d.record_of_rights, T = d.derived.labels.terms, v = d.derived.valuation;
  const mine = isCitizen() && ror.owner_id === S.me.person_id;
  const zc = d.zone_code;
  let h = `<h3 class="mono">${esc(d.ulpin)}</h3><div>${badge(zc + ' · ' + (ZONE_NAMES[zc] || ''), 'blue')}${badge(d.district + ', ' + d.state)}${d.privacy.public_visible ? '' : badge('Private', 'amber')}${mine ? badge(t('my_plots'), 'green') : ''}${d.satellite_watch.under_watch ? badge('Satellite watch', 'purple') : ''}</div>`;
  if (d.pending_mutation) h += `<div class="banner warn" style="margin-top:8px">${esc(t('pending_mutation'))} <span class="mono">${esc(d.pending_mutation.deed_no)}</span></div>`;

  h += sec(`${esc(t('record_of_rights'))} <span class="terms">— ${term(T.record_of_rights)}</span>`, kv([
    [esc(t('owner')), `<b>${esc(ror.owner_name)}</b> <span class="mono small">${esc(ror.owner_id)}</span>`],
    [term(T.survey_number), esc(d.survey_number)],
    [esc(t('area')), esc(d.derived.area.text)],
    ['Place', esc(d.place_name) + (d.landmark ? ' · ' + esc(d.landmark) : '')],
    ['RD no.', esc(d.rd_no || '—')],
    [esc(t('past_owners')), ror.past_owners.length ? ror.past_owners.map(esc).join(', ') : '—'],
    ['Last updated', esc(ror.ror_last_updated)]]));

  h += sec(esc(t('ownership_history')), `<ul class="tl">${d.ownership_history.map((e, i, a) =>
    `<li class="${i === a.length - 1 ? 'now' : ''}"><b>${esc(e.owner_name)}</b>${e.owner_id ? ` <span class="mono small">${esc(e.owner_id)}</span>` : ''}<br><span class="muted">${esc(e.basis)} · ${esc(e.from_date || 'date unknown')} → ${i === a.length - 1 ? 'present' : esc(e.to_date || '?')}</span></li>`).join('')}</ul>`);

  h += sec(esc(t('registration')), kv([['Latest owner (registration)', esc(d.registration.latest_owner_name)], ['Type', esc(d.registration.transaction_type)],
    ['Date', esc(d.registration.last_transaction_date)], ['Reg. no.', `<span class="mono">${esc(d.registration.registration_no)}</span>`]]));
  h += sec(esc(t('building')) + ' / ' + esc(t('land_use')), kv([[esc(t('building')), badge(d.building_permission.status, d.building_permission.status === 'Approved' ? 'green' : d.building_permission.status === 'Pending' ? 'amber' : '')],
    [esc(t('land_use')), esc(d.land_use_zoning.designated_use)], ['Master plan', esc(d.land_use_zoning.master_plan_ref)]]));
  h += sec(esc(t('encumbrance')), d.encumbrance.has_encumbrance ? badge('Encumbered', 'red') + ' ' + esc(d.encumbrance.details) : badge('Clear', 'green'));
  h += sec(esc(t('tax')), kv([['Assessee', esc(d.property_tax.assessee_name)], ['Annual tax', inr(d.property_tax.annual_tax_due)],
    [esc(t('status')), badge(d.property_tax.status, d.property_tax.status === 'Paid' ? 'green' : 'red')], ['Last paid', esc(d.property_tax.last_paid || '—')]]));
  h += sec(esc(t('utilities')), `${badge(d.utilities.water_connection ? 'Water ✔' : 'Water ✕', d.utilities.water_connection ? 'green' : 'red')}${badge(d.utilities.electricity_connection ? 'Power ✔' : 'Power ✕', d.utilities.electricity_connection ? 'green' : 'red')}`);
  h += sec(esc(t('valuation')), `${inr(v.guideline_per_sqm)}/sq.m × ${esc(d.derived.area.sqm)} sq.m = <b>${inr(v.guideline_value)}</b><div class="muted small">${esc(v.note)}</div>`);

  if (d.bank_link.restricted) h += sec(esc(t('bank')), `<span class="muted small">${esc(d.bank_link.message)}</span>`);
  else h += sec(esc(t('bank')), '<div id="bankBox" class="muted small">Loading…</div>');
  if (mine) h += sec(esc(t('privacy')), `<label class="check"><input type="checkbox" id="privChk" ${d.privacy.public_visible ? 'checked' : ''}> ${esc(t('show_my_name'))}</label>`);
  if (d.satellite_watch.under_watch) h += sec('Satellite analysis', '<button class="btn small" id="satBtn">View before / after</button><div id="satBox" style="margin-top:8px"></div>');
  if (isOfficer()) h += sec('Officer actions', `<div class="row">${role() === 'registration_officer' ? '<button class="btn small blue" id="actDeed">Start sale deed</button>' : ''}<button class="btn small" id="actReq">Record-update request</button><button class="btn small" id="actUpd">Post update for this plot</button></div>`);
  box.innerHTML = h;

  if ($('bankBox')) renderBank(d.ulpin);
  if ($('privChk')) $('privChk').onchange = async e => {
    const r = await post(`/api/parcel/${d.ulpin}/privacy`, { public_visible: e.target.checked });
    toast(r.ok ? 'Privacy setting saved' : (r.data && r.data.error)); await loadParcels(); selectParcel(d.ulpin, false);
  };
  if ($('satBtn')) $('satBtn').onclick = () => loadSatInline(d.ulpin, $('satBox'));
  if ($('actDeed')) $('actDeed').onclick = () => { showTab('deeds'); $('dUlpin').value = d.ulpin; };
  if ($('actReq')) $('actReq').onclick = () => { showTab('requests'); $('rqUlpin').value = d.ulpin; };
  if ($('actUpd')) $('actUpd').onclick = () => { showTab('updates'); $('upUlpin').value = d.ulpin; };
}

async function renderBank(ulpin) {
  const box = $('bankBox'); if (!box) return;
  const r = await api(`/api/parcel/${ulpin}/bank`);
  if (!r.ok) { box.innerHTML = `<span class="muted">${errText(r)}</span>`; return; }
  const b = r.data;
  if (!b.linked) {
    box.innerHTML = `<p class="muted small">Link a bank account (only the last 4 digits are stored) to check loan and mortgage status. Visible to you only.</p>
      <div class="row"><input id="bkName" placeholder="Bank name" style="padding:8px;border:1px solid var(--border);border-radius:8px"><input id="bkNum" placeholder="Account number" inputmode="numeric" style="padding:8px;border:1px solid var(--border);border-radius:8px"></div>
      <button class="btn small blue" id="bkLink" style="margin-top:6px">Link account</button>`;
    $('bkLink').onclick = async () => {
      const x = await post(`/api/parcel/${ulpin}/link-bank`, { bank_name: $('bkName').value, account_number: $('bkNum').value });
      toast(x.ok ? 'Bank linked' : (x.data && x.data.error)); renderBank(ulpin);
    };
    return;
  }
  const l = b.loan_summary;
  box.innerHTML = kv([['Bank', `${esc(b.bank_name)} ••••${esc(b.account_last4)}`], ['Mortgage', badge(l.mortgage_status, l.mortgage_status === 'Clear' ? 'green' : 'red')],
    ['Loan status', esc(l.status)], ['Loan amount', inr(l.loan_amount)], ['EMI', inr(l.emi)]]) + '<button class="btn small danger" id="bkUnlink" style="margin-top:6px">Unlink</button>';
  $('bkUnlink').onclick = async () => { await post(`/api/parcel/${ulpin}/unlink-bank`); renderBank(ulpin); };
}
async function loadSatInline(ulpin, box) {
  box.innerHTML = '<span class="muted small">Loading…</span>';
  const r = await api(`/api/parcel/${ulpin}/satellite`);
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  const s = r.data;
  box.innerHTML = `<div>${badge(s.flag ? 'Possible unauthorised change' : 'No concern', s.flag ? 'red' : 'green')} ${badge(s.change_pct + '% changed')}</div><p class="small">${esc(s.reason)}</p>
    <div class="row"><figure style="margin:0"><img src="${esc(s.before_image_url)}" alt="Before" style="width:100%;border-radius:8px"><figcaption class="small muted">Before</figcaption></figure>
    <figure style="margin:0"><img src="${esc(s.after_image_url)}" alt="After" style="width:100%;border-radius:8px"><figcaption class="small muted">After</figcaption></figure></div>
    <div class="muted small">Synthetic imagery for the demo; production would use real satellite tiles.</div>`;
}

// ---- search / citizen views ------------------------------------------------------------------
async function runSearch() {
  const q = $('searchQ').value.trim(); const box = $('searchResults');
  if (q.length < 2) { box.innerHTML = '<span class="muted">Type at least 2 characters.</span>'; return; }
  const r = await api('/api/search?q=' + encodeURIComponent(q));
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  if (!r.data.length) { box.innerHTML = `<span class="muted">${esc(t('no_results'))}</span>`; return; }
  box.innerHTML = `<div class="tablewrap"><table><tr><th>${esc(t('ulpin'))}</th><th>${esc(t('owner'))}</th><th>Location</th><th>${esc(t('zone'))}</th><th>${esc(t('survey_no'))}</th></tr>${r.data.map(x =>
    `<tr><td><button class="btn small mono" data-open="${esc(x.ulpin)}">${esc(x.ulpin)}</button></td><td>${x.owner_name ? esc(x.owner_name) : '<i>Private</i>'}</td><td>${esc(x.district)}</td><td>${esc(x.zone_code)}</td><td>${esc(x.survey_number)}</td></tr>`).join('')}</table></div>`;
  box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openOnMap(b.dataset.open));
}
async function loadMyLand() {
  const box = $('mylandList'); const r = await api('/api/my-properties');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  if (!r.data.length) { box.innerHTML = '<div class="card muted">You do not own any registered land yet.</div>'; return; }
  box.innerHTML = `<div class="grid">${r.data.map(p => `<div class="card"><h3 class="mono">${esc(p.ulpin)}</h3><div>${badge(p.zone_code + ' · ' + (ZONE_NAMES[p.zone_code] || ''), 'blue')}${badge(p.district)}</div>
    <p class="small">${esc(p.location_label)}</p><p><b>${esc(p.area.text)}</b></p><button class="btn small blue" data-open="${esc(p.ulpin)}">View on map</button></div>`).join('')}</div>`;
  box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openOnMap(b.dataset.open));
}
async function loadTransactions() {
  const box = $('txnList'); const r = await api('/api/deeds');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  box.innerHTML = r.data.length ? r.data.map(d => deedCard(d, 'citizen')).join('') : '<div class="card muted">No sale transactions involve you yet.</div>';
  bindDeedCards(box);
}
async function loadUpdates() {
  $('updateFormBox').classList.toggle('hidden', !isOfficer());
  const box = $('updatesList'); const r = await api('/api/updates');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  box.innerHTML = r.data.length ? r.data.map(u => `<div class="card"><h3>${esc(u.title)}</h3><div>${u.ulpin ? badge('Plot ' + u.ulpin, 'blue') : badge('District-wide')}${badge(u.district)}</div>
    <p style="white-space:pre-wrap">${esc(u.message)}</p><div class="muted small">${esc(u.posted_by)} · ${when(u.posted_at)}</div></div>`).join('') : '<div class="card muted">No updates.</div>';
}

// ---- sale deeds ----------------------------------------------------------------------------
function stepperHtml(status) {
  if (status === 'CANCELLED') return '<div class="stepper"><div class="step bad">Cancelled</div></div>';
  const idx = DEED_STEPS.findIndex(s => s[0] === status);
  return `<div class="stepper">${DEED_STEPS.map((s, i) => `<div class="step ${status === 'MUTATED' || i < idx ? 'done' : i === idx ? 'cur' : ''}">${esc(s[1])}</div>`).join('')}</div>`;
}
const DEED_HINT = {
  DRAFT: 'Waiting for the seller and the buyer to authenticate with the OTP sent to their mobiles.',
  AUTHENTICATED: 'Both parties verified. Waiting for stamp duty and registration fee to be paid.',
  PAID: 'Fees paid. Waiting for the Registration Officer to register the deed.',
  REGISTERED: 'Deed registered. The Revenue department now updates the Record of Rights (mutation).',
  MUTATED: 'Complete — the Record of Rights, ownership history and tax assessee now show the buyer.',
  CANCELLED: 'This deed was cancelled.'
};
function deedCard(d, mode) {
  const me = S.me.person_id;
  const who = mode === 'citizen' ? (d.seller_id === me ? badge('You are the seller', 'amber') : badge('You are the buyer', 'green')) : '';
  let h = `<div class="card" data-deed-card="${esc(d.id)}"><div class="row" style="justify-content:space-between"><h3 class="mono" style="flex:0 1 auto">${esc(d.id)}${d.deed_no ? ' · ' + esc(d.deed_no) : ''}</h3><div style="flex:0 1 auto">${who}</div></div>
    <p class="small">Plot <button class="btn small mono" data-open="${esc(d.ulpin)}">${esc(d.ulpin)}</button> ${d.parcel ? '· survey ' + esc(d.parcel.survey_number) : ''} · ${esc(d.district)}</p>
    ${stepperHtml(d.status)}<p class="muted small">${esc(DEED_HINT[d.status])}</p>
    ${kv([['Seller', `${esc(d.seller_name)} <span class="mono small">${esc(d.seller_id)}</span>`], ['Buyer', `${esc(d.buyer_name)} <span class="mono small">${esc(d.buyer_id)}</span>`],
      ['Sale price', inr(d.consideration)], ['Guideline value', inr(d.guideline_value)], ['Assessed on', inr(d.assessed_value)],
      [`Stamp duty (${esc(d.rates.stamp_duty_pct)}%)`, inr(d.stamp_duty)], [`Registration fee (${esc(d.rates.registration_fee_pct)}%)`, inr(d.registration_fee)], ['Total fees', `<b>${inr(d.total_fees)}</b>`]])}
    <div class="muted small">${esc(d.rates.note)}</div>`;
  if (mode === 'officer') h += deedActions(d);
  h += `<details style="margin-top:8px"><summary class="small">Timeline</summary><ul class="tl">${d.timeline.map(e => `<li><b>${esc(e.status)}</b> · ${when(e.at)}<br><span class="muted">${esc(e.note)} — ${esc(e.by)}</span></li>`).join('')}</ul></details></div>`;
  return h;
}
function deedActions(d) {
  const r = role(); const id = esc(d.id); let h = '<div class="dsec">';
  if (d.status === 'DRAFT' && r === 'registration_officer') {
    const sms = S.demoOtps[d.id];
    if (sms) h += `<div class="sms">📱 ${esc(t('demo_otp'))} — in production each code goes only to that person's phone:${Object.entries(sms).map(([p, x]) => `<br>${esc(p)} (${esc(x.name)}, ${esc(x.mobile)}): <b>${esc(x.otp)}</b>`).join('')}</div>`;
    ['seller', 'buyer'].forEach(p => {
      h += d.auth[p].verified ? `<div class="chk ok">✔ ${p} (${esc(d[p + '_name'])}) authenticated</div>`
        : `<div class="row" style="align-items:end"><label class="f" style="margin:0"><span>${p} (${esc(d[p + '_name'])}) reads out the OTP</span><input data-otp="${p}" data-deed="${id}" inputmode="numeric" maxlength="6"></label><button class="btn small blue" style="flex:0 0 auto" data-act="auth" data-party="${p}" data-deed="${id}">${esc(t('verify'))}</button></div>`;
    });
    h += `<div class="row" style="margin-top:8px"><button class="btn small" data-act="resend" data-deed="${id}">Resend OTPs</button><button class="btn small danger" data-act="cancel" data-deed="${id}">Cancel deed</button></div>`;
  } else if (d.status === 'AUTHENTICATED' && r === 'registration_officer') {
    h += `<div class="row" style="align-items:end"><label class="f" style="margin:0"><span>Challan / payment reference for ${inr(d.total_fees)}</span><input data-challan="${id}" maxlength="40"></label><button class="btn small blue" style="flex:0 0 auto" data-act="pay" data-deed="${id}">Record payment</button><button class="btn small danger" style="flex:0 0 auto" data-act="cancel" data-deed="${id}">Cancel</button></div>`;
  } else if (d.status === 'PAID' && r === 'registration_officer') {
    h += `<div class="row"><button class="btn blue" data-act="register" data-deed="${id}">Register deed</button><button class="btn danger" data-act="cancel" data-deed="${id}">Cancel (refund fees)</button></div>`;
  } else if (d.status === 'REGISTERED') {
    h += r === 'revenue_officer' ? `<button class="btn blue" data-act="mutate" data-deed="${id}">Complete mutation (update Record of Rights)</button>` : '<div class="banner info">Waiting for the Revenue Officer to complete the mutation.</div>';
  } else { h += '<span class="muted small">No action required.</span>'; }
  return h + '</div>';
}
function bindDeedCards(root) {
  root.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openOnMap(b.dataset.open));
  root.querySelectorAll('[data-act]').forEach(b => b.onclick = () => deedAction(b.dataset.deed, b.dataset.act, b.dataset.party));
}
async function deedAction(id, act, party) {
  let url = `/api/deeds/${id}/`, body = {};
  if (act === 'auth') { url += 'authenticate'; body = { party, otp: (document.querySelector(`input[data-otp="${party}"][data-deed="${id}"]`) || {}).value }; }
  else if (act === 'pay') { url += 'payment'; body = { challan_no: (document.querySelector(`input[data-challan="${id}"]`) || {}).value }; }
  else url += act;
  const r = await post(url, body);
  if (!r.ok) { toast((r.data && r.data.error) || 'Failed', 6000); return; }
  if (act === 'resend' && r.data.demo_otps) S.demoOtps[id] = Object.assign({}, S.demoOtps[id] || {}, r.data.demo_otps);
  if (act === 'auth') { const sms = S.demoOtps[id]; if (sms) delete sms[party]; }
  toast({ auth: 'Verified', pay: 'Payment recorded', register: 'Deed registered', mutate: 'Mutation complete — Record of Rights updated', cancel: 'Deed cancelled', resend: 'New OTPs sent' }[act] || 'Done');
  if (['register', 'mutate'].includes(act)) await loadParcels();
  loadDeeds();
}
async function loadDeeds() {
  $('deedFormBox').classList.toggle('hidden', role() !== 'registration_officer');
  const box = $('deedList'); const r = await api('/api/deeds');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  const waiting = r.data.filter(d => d.status === 'REGISTERED').length;
  let intro = '';
  if (role() === 'revenue_officer') intro = `<div class="banner ${waiting ? 'warn' : 'info'}">${waiting} registered deed(s) awaiting your mutation.</div>`;
  box.innerHTML = intro + (r.data.length ? r.data.map(d => deedCard(d, 'officer')).join('') : '<div class="card muted">No sale deeds in this district yet.</div>');
  bindDeedCards(box);
}
async function createDeed() {
  const b = S.picks.buyer;
  const body = { ulpin: $('dUlpin').value.trim().toUpperCase(), buyer_id: b && b.person_id, consideration: $('dPrice').value.replace(/,/g, ''), bank_noc: $('dNoc').checked, notes: $('dNotes').value };
  const r = await post('/api/deeds', body);
  if (!r.ok) { toast((r.data && r.data.error) || 'Failed', 7000); return; }
  S.demoOtps[r.data.deed.id] = r.data.demo_otps || null;
  toast('Deed drafted — OTPs sent to seller and buyer');
  ['dUlpin', 'dPrice', 'dNotes'].forEach(i => { $(i).value = ''; }); $('dNoc').checked = false; S.picks.buyer = null; $('dBuyerPicked').classList.add('hidden');
  loadDeeds();
}

// ---- record-update requests ----------------------------------------------------------------
const REQUEST_TYPES = ['Succession / Inheritance', 'Name / Detail Correction', 'Encumbrance Certificate Update', 'Building Permission Correction'];
async function loadRequests() {
  const box = $('requestList'); const r = await api('/api/requests');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  box.innerHTML = r.data.length ? r.data.map(q => `<div class="card"><div class="row" style="justify-content:space-between"><h3 style="flex:0 1 auto">${esc(q.type)}</h3><div style="flex:0 1 auto">${badge(q.status, q.status === 'Approved' ? 'green' : q.status === 'Rejected' ? 'red' : 'amber')}</div></div>
    <p class="small"><button class="btn small mono" data-open="${esc(q.ulpin)}">${esc(q.ulpin)}</button> · initiated by ${esc(q.initiated_by)} with ${esc(q.citizen_name)} present · ${when(q.created_at)}${q.new_owner_name ? ' · heir: <b>' + esc(q.new_owner_name) + '</b>' : ''}</p>
    ${q.notes ? `<p class="small">${esc(q.notes)}</p>` : ''}
    ${q.status === 'Pending Approval' && role() === 'registration_officer' ? `<div class="row"><button class="btn small blue" data-rq="approve" data-id="${esc(q.id)}">Approve</button><button class="btn small danger" data-rq="reject" data-id="${esc(q.id)}">Reject</button></div>` : ''}</div>`).join('') : '<div class="card muted">No requests.</div>';
  box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openOnMap(b.dataset.open));
  box.querySelectorAll('[data-rq]').forEach(b => b.onclick = async () => {
    const x = await post(`/api/requests/${b.dataset.id}/${b.dataset.rq}`);
    toast(x.ok ? 'Done' : (x.data && x.data.error)); if (x.ok) { await loadParcels(); loadRequests(); }
  });
}
async function createRequest() {
  const type = $('rqType').value; const heir = S.picks.heir;
  const r = await post(`/api/parcel/${$('rqUlpin').value.trim().toUpperCase()}/service-request`, { type, citizen_name: $('rqCitizen').value, citizen_present: $('rqPresent').checked, new_owner_id: heir && heir.person_id, notes: $('rqNotes').value });
  if (!r.ok) { toast((r.data && r.data.error) || 'Failed', 6000); return; }
  toast('Request submitted for approval'); $('rqNotes').value = ''; $('rqPresent').checked = false; loadRequests();
}

// ---- register land: draw the boundary ------------------------------------------------------
async function initRegister() {
  const r = await api('/api/parcels/district-defaults');
  if (!r.ok) { toast((r.data && r.data.error) || 'Could not load defaults'); return; }
  const dfl = r.data, first = !S.regMap; S.regDefaults = dfl;
  if (first) {
    S.regMap = L.map('regMap').setView([dfl.center_latitude, dfl.center_longitude], 17);
    L.tileLayer(MAP_TILES.url, { attribution: MAP_TILES.attribution, maxZoom: MAP_TILES.maxZoom }).addTo(S.regMap);
    S.regExisting = L.layerGroup().addTo(S.regMap); S.regDrawGroup = L.layerGroup().addTo(S.regMap);
    S.regMap.on('click', e => addRegPoint(e.latlng));
    $('rgUse').innerHTML = dfl.zoning_options.map(z => `<option>${esc(z)}</option>`).join('');
  }
  S.regExisting.clearLayers(); S.regPolys = {};
  L.circle([dfl.center_latitude, dfl.center_longitude], { radius: dfl.jurisdiction_km * 1000, color: '#0f4c81', weight: 1, dashArray: '6 6', fill: false, interactive: false }).addTo(S.regExisting);
  ((S.geo && S.geo.features) || []).filter(f => f.properties.district === dfl.district).forEach(f => {
    S.regPolys[f.properties.ulpin] = L.polygon(f.geometry.coordinates[0].map(c => [c[1], c[0]]), { color: '#7b8794', weight: 1, fillColor: '#b8c2cc', fillOpacity: 0.5, interactive: false }).addTo(S.regExisting);
  });
  if (first) {
    const ex = Object.values(S.regPolys)[0];
    if (ex) S.regMap.fitBounds(L.featureGroup(Object.values(S.regPolys)).getBounds().pad(0.15), { maxZoom: 18 });
  }
  setTimeout(() => S.regMap.invalidateSize(), 80);
  fillRegDefaults(false);
  const ad = await api('/api/adapters');
  if (ad.ok && !$('rgImportJson').value) {
    const f = (ad.data[dfl.state] || {}).ingestion_fields || {}, ex = {};
    const sample = { ror_reference: 'REF-1234', survey_number: '120/3A', sub_division: '3A', owner_name: 'Owner Name', place_name: dfl.place_name };
    Object.entries(f).forEach(([k, v]) => { ex[k] = v.startsWith('extent:') ? (/acre|kanal|bigha/.test(v) ? 0 : 12.5) : (sample[v] || 'x'); });
    $('rgImportJson').value = JSON.stringify(ex, null, 2);
  }
  redrawReg();
}
function fillRegDefaults(force) {
  const d = S.regDefaults; if (!d) return;
  const set = (id, v) => { if (force || !$(id).value) $(id).value = v || ''; };
  set('rgUlpin', d.ulpin_suggestion); set('rgSurvey', d.survey_number_suggestion); set('rgPlace', d.place_name); set('rgRd', d.rd_no_suggestion);
}
function addRegPoint(latlng) { S.regDraw.pts.push([+latlng.lat.toFixed(7), +latlng.lng.toFixed(7)]); redrawReg(); }
function redrawReg() {
  if (!S.regDrawGroup) return;
  S.regDrawGroup.clearLayers();
  const pts = S.regDraw.pts;
  if (pts.length >= 3) L.polygon(pts, { color: '#e08a00', weight: 3, fillOpacity: 0.25, interactive: false }).addTo(S.regDrawGroup);
  else if (pts.length === 2) L.polyline(pts, { color: '#e08a00', weight: 3, interactive: false }).addTo(S.regDrawGroup);
  pts.forEach((p, i) => L.circleMarker(p, { radius: 6, color: '#fff', weight: 2, fillColor: i === 0 ? '#1b7a43' : '#e08a00', fillOpacity: 1, interactive: false }).addTo(S.regDrawGroup));
  if (pts.length >= 3) checkBoundary();
  else { S.regValid = false; $('rgCheck').innerHTML = `<span class="muted">${pts.length ? 'Add at least 3 corners…' : 'Click the map to start drawing the plot boundary.'}</span>`; updateRegSubmit(); }
}
const checkBoundary = debounce(async () => {
  const r = await post('/api/geo/check-boundary', { boundary: S.regDraw.pts });
  if (!r.ok) { $('rgCheck').innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  const c = r.data, rows = [];
  const line = (ok, txt) => `<div class="chk ${ok ? 'ok' : 'no'}">${ok ? '✔' : '✖'} <span>${txt}</span></div>`;
  Object.values(S.regPolys || {}).forEach(p => p.setStyle({ color: '#7b8794', fillColor: '#b8c2cc' }));
  if (!c.area) { c.errors.forEach(e => rows.push(line(false, esc(e)))); }
  else {
    rows.push(line(true, 'Valid, non-self-intersecting shape'));
    let areaTxt = `Area computed from the boundary: <b>${esc(c.area.text)}</b>`;
    if (S.expectedArea) { const diff = (c.area.sqm - S.expectedArea) / S.expectedArea * 100; areaTxt += ` — record says ${esc(S.expectedArea)} sq.m (${diff >= 0 ? '+' : ''}${diff.toFixed(1)}%)`; }
    rows.push(line(true, areaTxt));
    rows.push(line(c.within_jurisdiction === true, c.within_jurisdiction ? 'Inside this district\'s jurisdiction' : 'Outside this district\'s jurisdiction'));
    if (c.overlaps.length) c.overlaps.forEach(o => { rows.push(line(false, `Overlaps <span class="mono">${esc(o.ulpin)}</span> (survey ${esc(o.survey_number)}) by ~${Math.round(o.fraction * 100)}% of the smaller plot`)); if (S.regPolys[o.ulpin]) S.regPolys[o.ulpin].setStyle({ color: '#c62828', fillColor: '#ef9a9a' }); });
    else rows.push(line(true, 'No overlap with registered plots'));
    c.errors.filter(e => !/jurisdiction|Overlaps/.test(e)).forEach(e => rows.push(line(false, esc(e))));
  }
  S.regValid = !!c.valid; $('rgCheck').innerHTML = rows.join(''); updateRegSubmit();
}, 300);
function updateRegSubmit() {
  const mode = document.querySelector('input[name=ownMode]:checked').value;
  const ownerOk = mode === 'existing' ? !!S.picks.owner : ($('rgNewName').value.trim().length >= 2 && /^\d{10}$/.test($('rgNewMobile').value.trim()));
  $('rgSubmit').disabled = !(S.regValid && ownerOk && $('rgSurvey').value.trim() && $('rgPlace').value.trim() && $('rgUlpin').value.trim());
}
async function submitRegistration() {
  const mode = document.querySelector('input[name=ownMode]:checked').value;
  const body = { ulpin: $('rgUlpin').value.trim().toUpperCase(), survey_number: $('rgSurvey').value, place_name: $('rgPlace').value, rd_no: $('rgRd').value, landmark: $('rgLandmark').value,
    designated_use: $('rgUse').value, boundary: S.regDraw.pts, past_owners: $('rgPast').value, notes: $('rgNotes').value };
  if (mode === 'existing') body.owner_id = S.picks.owner.person_id; else body.new_owner = { name: $('rgNewName').value, mobile: $('rgNewMobile').value.trim() };
  $('rgSubmit').disabled = true;
  const r = await post('/api/parcels/register', body);
  if (!r.ok) { $('rgResult').innerHTML = `<div class="banner err">${errText(r)}</div>`; updateRegSubmit(); return; }
  const p = r.data.parcel, acc = r.data.new_citizen_account;
  $('rgResult').innerHTML = `<div class="banner ok"><b>Registered.</b> ULPIN <span class="mono">${esc(p.ulpin)}</span> · ${esc(r.data.area.text)}<br>Owner: ${esc(r.data.person.name)} <span class="mono">${esc(r.data.person.person_id)}</span></div>
    ${acc ? `<div class="banner warn"><b>New citizen account — give these to the owner now (shown once):</b><br>Username <span class="mono">${esc(acc.username)}</span> · Password <span class="mono">${esc(acc.password)}</span><br><span class="small">${esc(acc.note)}</span></div>` : ''}
    <button class="btn small" id="rgView">View on map</button>`;
  $('rgView').onclick = () => openOnMap(p.ulpin);
  S.regDraw.pts = []; S.expectedArea = null; S.picks.owner = null; $('rgOwnerPicked').classList.add('hidden');
  ['rgLandmark', 'rgPast', 'rgNotes', 'rgNewName', 'rgNewMobile'].forEach(i => { $(i).value = ''; });
  await loadParcels(); await initRegister(); fillRegDefaults(true); toast('Parcel registered');
}
async function previewImport() {
  const out = $('rgImportOut'); let rec;
  try { rec = JSON.parse($('rgImportJson').value); } catch (e) { out.innerHTML = '<div class="banner err">That is not valid JSON.</div>'; return; }
  const r = await post('/api/adapters/normalize', { record: rec });
  if (!r.ok) { out.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  const c = r.data; S.importCanon = c.canonical;
  out.innerHTML = `<div class="tablewrap"><table><tr><th>Canonical field</th><th>Value</th></tr>${Object.entries(c.canonical).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table></div>
    ${c.conversions.map(x => `<p class="small">Unit conversion: ${esc(JSON.stringify(x.from))} → ${esc(x.to.sqm)} sq.m</p>`).join('')}
    ${c.unrecognised_fields.length ? `<p class="small muted">Ignored: ${c.unrecognised_fields.map(esc).join(', ')}</p>` : ''}
    ${c.warnings.map(w => `<div class="banner warn">${esc(w)}</div>`).join('')}`;
  $('rgImportApply').classList.remove('hidden');
}
function applyImport() {
  const c = S.importCanon || {};
  if (c.survey_number) $('rgSurvey').value = c.survey_number;
  if (c.place_name) $('rgPlace').value = c.place_name;
  if (c.ror_reference) $('rgNotes').value = `Imported from state record ${c.ror_reference}`;
  if (c.area_sqm) S.expectedArea = c.area_sqm;
  if (c.owner_name) { $('rgOwnerQ').value = c.owner_name; $('rgOwnerQ').dispatchEvent(new Event('input')); }
  toast('Applied — now draw the boundary; it will be compared with the record\'s area'); redrawReg(); updateRegSubmit();
}

// ---- risk / model card ----------------------------------------------------------------------
async function loadRisk() {
  const box = $('riskTable'); const r = await api('/api/anomalies');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  if (!r.data.length) { box.innerHTML = '<span class="muted">No parcels need attention.</span>'; return; }
  box.innerHTML = `<table><tr><th>Plot</th><th>Rule-based findings</th><th>Rule score</th><th>Learned risk</th><th>Main contributing factors</th></tr>${r.data.map(a => {
    const pct = Math.round(a.ml_risk * 100);
    return `<tr><td><button class="btn small mono" data-open="${esc(a.ulpin)}">${esc(a.ulpin)}</button></td>
      <td>${a.issues.length ? a.issues.map(i => `<div>${esc(i)}</div>`).join('') : '<span class="muted">none</span>'}<div class="small muted">RoR: ${esc(a.ror_owner)} · Reg: ${esc(a.registration_owner)} · Tax: ${esc(a.tax_owner)}</div></td>
      <td>${esc(a.risk_score)}</td><td style="min-width:120px"><div class="bar"><span style="width:${pct}%;background:${pct >= 60 ? '#c62828' : pct >= 35 ? '#e08a00' : '#3fb37f'}"></span></div>${pct}%</td>
      <td>${a.top_factors.length ? a.top_factors.map(f => badge(f.label + ' (+' + f.contribution + ')', 'amber')).join('') : '<span class="muted">—</span>'}</td></tr>`;
  }).join('')}</table>`;
  box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openOnMap(b.dataset.open));
}
async function showModelCard() {
  const box = $('modelCard'); const r = await api('/api/ml/model-card');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  const c = r.data, w = Object.entries(c.learned_weights_standardised).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])), mx = Math.max(...w.map(x => Math.abs(x[1])));
  const lab = Object.fromEntries(c.features.map(f => [f.name, f.label]));
  box.innerHTML = `<div class="banner warn"><b>Read this first:</b> ${esc(c.training_data)}. The scores below measure how well the model recovers a <i>synthetic</i> process — not real-world accuracy.</div>
    <div class="grid"><div class="kpi">${c.auc_test}<small>AUC (held-out)</small></div><div class="kpi">${c.auc_rule_baseline}<small>AUC of the rule baseline</small></div><div class="kpi">${Math.round(c.precision_top_decile * 100)}%<small>precision in top 10%</small></div><div class="kpi">${Math.round(c.recall_top_decile * 100)}%<small>recall in top 10%</small></div><div class="kpi">${Math.round(c.dispute_base_rate * 100)}%<small>base rate in data</small></div></div>
    <h4 style="margin-top:12px">What the model learned (standardised weights)</h4>
    ${w.map(([k, v]) => `<div class="row" style="align-items:center;gap:8px"><div style="flex:0 0 260px" class="small">${esc(lab[k])}</div><div class="bar" style="flex:1"><span style="width:${Math.abs(v) / mx * 100}%"></span></div><div class="mono small" style="flex:0 0 50px">${v}</div></div>`).join('')}
    <h4 style="margin-top:12px">Limitations</h4><ul>${c.limitations.map(l => `<li class="small">${esc(l)}</li>`).join('')}</ul><div class="muted small">Model: ${esc(c.model)} · ${esc(c.test_data)}</div>`;
}

// ---- satellite / reports / audit ------------------------------------------------------------
async function loadSatellite() {
  const box = $('satList'); const r = await api('/api/satellite-watchlist');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  box.innerHTML = r.data.length ? r.data.map(w => `<div class="card"><div class="row" style="justify-content:space-between"><h3 class="mono" style="flex:0 1 auto">${esc(w.ulpin)}</h3><div style="flex:0 1 auto">${badge(w.flag ? 'Possible unauthorised change' : 'No concern', w.flag ? 'red' : 'green')}${badge(w.change_pct + '% changed')}</div></div>
    <p class="small">${esc(w.designated_use)} — ${esc(w.reason)}</p><button class="btn small" data-sat="${esc(w.ulpin)}">View before / after</button> <button class="btn small" data-open="${esc(w.ulpin)}">On map</button><div id="sat-${esc(w.ulpin)}" style="margin-top:8px"></div></div>`).join('') : '<div class="card muted">No plots under satellite watch in this district.</div>';
  box.querySelectorAll('[data-sat]').forEach(b => b.onclick = () => loadSatInline(b.dataset.sat, $('sat-' + b.dataset.sat)));
  box.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openOnMap(b.dataset.open));
}
function barList(obj) {
  const mx = Math.max(1, ...Object.values(obj));
  return Object.entries(obj).map(([k, v]) => `<div class="row" style="align-items:center;gap:8px"><div style="flex:0 0 150px" class="small">${esc(k)}</div><div class="bar" style="flex:1"><span style="width:${v / mx * 100}%"></span></div><div class="mono small" style="flex:0 0 40px">${esc(v)}</div></div>`).join('') || '<span class="muted small">—</span>';
}
async function loadReports() {
  const box = $('reportBox'); const r = await api('/api/reports');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  const d = r.data, k = (v, l) => `<div class="card"><div class="kpi">${v}<small>${esc(l)}</small></div></div>`;
  box.innerHTML = `<h2>${esc(d.district)} District</h2><div class="grid">${k(d.total_parcels, 'Parcels')}${k(inr(d.total_tax_due), 'Property tax outstanding')}${k(d.encumbrance_count, 'Encumbered plots')}${k(d.anomaly_count, 'Record mismatches')}${k(d.pending_mutations, 'Mutations pending')}${k(d.new_registrations, 'Registered via this system')}${k(inr(d.fees_collected), 'Duty & fees collected')}${k(d.linked_bank_count, 'Owners with bank linked')}${k(d.satellite_flagged_count + '/' + d.satellite_watchlist_count, 'Satellite flags / watched')}</div>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(280px,1fr))"><div class="card"><h4>Land use</h4>${barList(d.by_zoning)}</div><div class="card"><h4>Property tax</h4>${barList(d.tax_status)}</div><div class="card"><h4>Sale deeds by status</h4>${barList(d.deeds_by_status)}</div><div class="card"><h4>Record-update requests</h4>${barList(d.requests_by_status)}</div></div>`;
}
async function loadAudit() {
  const box = $('auditTable'); const r = await api('/api/audit-log');
  if (!r.ok) { box.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  box.innerHTML = `<table><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Plot</th><th>Details</th><th>Hash</th></tr>${r.data.map(e => `<tr><td>${esc(e.seq)}</td><td class="small">${when(e.timestamp)}</td><td>${esc(e.actor)}</td><td><span class="badge">${esc(e.action)}</span></td><td class="mono small">${esc(e.ulpin || '')}</td><td class="small">${esc(e.details)}</td><td class="mono small" title="${esc(e.hash)}">${esc(e.hash.slice(0, 10))}…</td></tr>`).join('')}</table>`;
}
async function verifyAudit() {
  const r = await api('/api/audit-log/verify'); const out = $('auditVerifyOut');
  if (!r.ok) { out.innerHTML = `<div class="banner err">${errText(r)}</div>`; return; }
  const v = r.data;
  out.innerHTML = v.valid ? `<div class="banner ok">✔ Chain intact — ${esc(v.entries)} entries verified.<br><span class="small">Head hash (anchor this externally): <span class="mono">${esc(v.head_hash)}</span></span></div>`
    : `<div class="banner err">✖ Tampering detected at entry #${esc(v.first_bad_seq)}: ${esc(v.reason)}</div>`;
}

// ---- startup --------------------------------------------------------------------------------
function currentPortal() { return location.pathname.startsWith('/officer') ? 'officer' : location.pathname.startsWith('/citizen') ? 'citizen' : 'public'; }
function bindStatic() {
  $('loginBtn').onclick = () => { const p = currentPortal(); p === 'public' ? openLoginChooser() : openLogin(p); };
  $('logoutBtn').onclick = doLogout;
  $('langSel').innerHTML = Object.entries(LANGS).map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join(''); $('langSel').value = LANG;
  $('langSel').onchange = e => { setLang(e.target.value); renderHeader(); buildTabs(); showTab(S.tab); renderLegend(); if (S.lastDetail) renderDossier(S.lastDetail); };
  $('regionSel').onchange = e => { S.region = e.target.value; fitRegion(); };
  $('fitBtn').onclick = fitRegion;
  $('layersBtn').onclick = () => $('layerPanel').classList.toggle('collapsed');
  ['lyBounds', 'lyLabels', 'lyTax', 'lySat', 'lyUtil'].forEach(i => $(i).onchange = renderParcels);
  document.querySelectorAll('input[name=colorBy]').forEach(r => r.onchange = renderParcels);
  $('searchBtn').onclick = runSearch; $('searchQ').addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });
  $('upPost').onclick = async () => {
    const r = await post('/api/updates', { title: $('upTitle').value, message: $('upMsg').value, ulpin: $('upUlpin').value });
    if (!r.ok) { toast((r.data && r.data.error) || 'Failed', 5000); return; }
    ['upTitle', 'upMsg', 'upUlpin'].forEach(i => { $(i).value = ''; }); toast('Update posted'); loadUpdates();
  };
  $('dCreate').onclick = createDeed;
  $('rqType').innerHTML = REQUEST_TYPES.map(x => `<option>${esc(x)}</option>`).join('');
  $('rqType').onchange = () => $('rqHeirBox').classList.toggle('hidden', !$('rqType').value.startsWith('Succession'));
  $('rqCreate').onclick = createRequest;
  $('modelCardBtn').onclick = showModelCard; $('auditVerifyBtn').onclick = verifyAudit;
  // register tab
  personPicker('rgOwnerQ', 'rgOwnerResults', 'rgOwnerPicked', 'owner', updateRegSubmit);
  personPicker('dBuyerQ', 'dBuyerResults', 'dBuyerPicked', 'buyer');
  personPicker('rqHeirQ', 'rqHeirResults', 'rqHeirPicked', 'heir');
  document.querySelectorAll('input[name=ownMode]').forEach(r => r.onchange = () => {
    const isNew = document.querySelector('input[name=ownMode]:checked').value === 'new';
    $('ownExisting').classList.toggle('hidden', isNew); $('ownNew').classList.toggle('hidden', !isNew); updateRegSubmit();
  });
  ['rgUlpin', 'rgSurvey', 'rgPlace', 'rgNewName', 'rgNewMobile'].forEach(i => $(i).addEventListener('input', updateRegSubmit));
  $('rgUndo').onclick = () => { S.regDraw.pts.pop(); redrawReg(); };
  $('rgClear').onclick = () => { S.regDraw.pts = []; redrawReg(); };
  $('rgSubmit').onclick = submitRegistration; $('rgImportBtn').onclick = previewImport; $('rgImportApply').onclick = applyImport;
  // PWA + connectivity
  window.addEventListener('offline', () => $('offlineBar').classList.remove('hidden'));
  window.addEventListener('online', () => $('offlineBar').classList.add('hidden'));
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); S.deferredInstall = e; $('installBtn').classList.remove('hidden'); });
  $('installBtn').onclick = async () => { if (S.deferredInstall) { S.deferredInstall.prompt(); S.deferredInstall = null; $('installBtn').classList.add('hidden'); } };
  if (!navigator.onLine) $('offlineBar').classList.remove('hidden');
}
async function init() {
  initLang(); applyI18n(); bindStatic(); initMap();
  await refreshMe(); renderHeader(); buildTabs(); await loadRegions(); await loadParcels();
  if (S.me.logged_in) {
    if (S.me.role !== 'citizen' && S.me.region) S.region = S.me.region;
    else if (S.me.role === 'citizen' && S.me.owned_ulpins && S.me.owned_ulpins.length) { const f = S.geo.features.find(x => x.properties.ulpin === S.me.owned_ulpins[0]); if (f) S.region = f.properties.context; }
    $('regionSel').value = S.region;
  }
  showTab('map'); fitRegion();
  const p = currentPortal();
  if (!S.me.logged_in && p !== 'public') openLogin(p);
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname))) navigator.serviceWorker.register('/sw.js').catch(() => { });
}
init();
