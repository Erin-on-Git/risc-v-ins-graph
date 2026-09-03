const search = document.querySelector('#search');
const list = document.querySelector('#extension-list');
const detailPanel = document.querySelector('#detail-panel');
const empty = document.querySelector('#empty');
let type = 'all';
let selected = null;
let timer;
let graphZoom = 1;

const api = (path) => fetch(path).then((response) => response.json());
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
const label = (value) => value ? String(value).replaceAll('_', ' ') : '';

async function loadSummary() {
  const { counts } = await api('/api/summary');
  document.querySelector('#source-count').textContent = `${counts.extensions} EXTENSIONS`;
  document.querySelector('#stats').innerHTML = [
    ['Extensions', counts.extensions], ['Instructions', counts.instructions], ['Profiles', counts.profiles], ['Versions', counts.extension_versions]
  ].map(([name, value]) => `<div class="stat"><strong>${value.toLocaleString()}</strong><span>${name}</span></div>`).join('');
}

async function loadExtensions() {
  const rows = await api(`/api/extensions?search=${encodeURIComponent(search.value)}&type=${type}`);
  document.querySelector('#result-count').textContent = `${rows.length} results`;
  document.querySelector('#result-meta').textContent = rows.length ? `${rows.length} records` : '';
  empty.style.display = rows.length ? 'none' : 'grid';
  list.innerHTML = rows.map((row) => `<button class="extension-row ${selected === row.name ? 'selected' : ''}" data-name="${esc(row.name)}"><span class="extension-name">${esc(row.name)}</span><span class="extension-copy"><b>${esc(row.long_name || 'No description')}</b><small>${esc(row.type || 'profile-defined')}</small></span><span class="chevron">›</span></button>`).join('');
  list.querySelectorAll('.extension-row').forEach((row) => row.addEventListener('click', () => selectExtension(row.dataset.name)));
}

function chips(items, className = '') {
  return items.length ? `<div class="chips">${items.map((item) => `<span class="chip ${className}">${esc(item)}</span>`).join('')}</div>` : '<span class="muted">None recorded</span>';
}

async function selectExtension(name) {
  selected = name;
  graphZoom = 1;
  await loadExtensions();
  const result = await api(`/api/extensions/${encodeURIComponent(name)}`);
  const ext = result.extension;
  detailPanel.innerHTML = `<article class="detail"><div class="detail-top"><div><div class="kicker">EXTENSION RECORD</div><h2>${esc(ext.name)}</h2><span class="badge ${ext.type === 'privileged' ? 'orange' : ''}">${esc(ext.type || 'profile-defined')}</span></div><div class="record-id">ID ${esc(ext.extension_id)}</div></div><p class="description">${esc(ext.description || ext.long_name || 'No description available.')}</p><section><div class="graph-heading"><h3>Relationship view</h3><div class="zoom-controls"><button id="zoom-out" title="Zoom out">−</button><button id="zoom-reset" title="Reset zoom">100%</button><button id="zoom-in" title="Zoom in">+</button></div></div><div class="detail-graph" id="detail-graph"></div><p class="graph-note">Dependencies point outward from this extension.</p></section><section><h3>Versions <span>${result.versions.length}</span></h3>${result.versions.length ? `<div class="version-table"><div class="table-head"><span>VERSION</span><span>STATE</span><span>RATIFIED</span></div>${result.versions.map((item) => `<div class="table-row"><b>${esc(item.version)}</b><span>${esc(item.state || 'development')}</span><span>${esc(item.ratification_date || '—')}</span></div>`).join('')}</div>` : '<span class="muted">No versions recorded</span>'}</section><section><h3>Extension dependencies <span>${result.dependencies.length}</span></h3>${chips(result.dependencies.map((item) => item.name))}</section><section><h3>Dependents <span>${result.dependents.length}</span></h3>${chips(result.dependents.map((item) => item.name), 'orange')}</section><section><h3>Instructions <span>${result.instructions.length}</span></h3>${chips(result.instructions.map((item) => item.name))}</section><section><h3>Included in profiles <span>${result.profiles.length}</span></h3>${chips(result.profiles.map((item) => item.name), 'yellow')}</section><section><h3>SQL executed <span>${result.queries.length} queries</span></h3><div class="sql-list">${result.queries.map((item) => `<div class="sql-item"><code>${esc(item.sql)}</code></div>`).join('')}</div></section></article>`;
  renderDetailGraph(ext, result.dependencies, result.dependents);
  document.querySelector('#zoom-in').addEventListener('click', () => { graphZoom = Math.min(3, graphZoom + .25); renderDetailGraph(ext, result.dependencies, result.dependents); });
  document.querySelector('#zoom-out').addEventListener('click', () => { graphZoom = Math.max(.5, graphZoom - .25); renderDetailGraph(ext, result.dependencies, result.dependents); });
  document.querySelector('#zoom-reset').addEventListener('click', () => { graphZoom = 1; renderDetailGraph(ext, result.dependencies, result.dependents); });
}

function renderDetailGraph(extension, dependencies, dependents) {
  const items = [...dependencies.map((item) => ({...item, relation: 'dependency'})), ...dependents.map((item) => ({...item, relation: 'dependent'}))];
  const width = 480; const height = Math.max(150, Math.min(260, 90 + items.length * 22)); const center = {x: width / 2, y: height / 2};
  const nodes = items.map((item, index) => ({...item, x: item.relation === 'dependency' ? 78 : width - 78, y: 30 + index * ((height - 60) / Math.max(1, items.length - 1))}));
  const lines = nodes.map((node) => `<line class="detail-edge ${node.relation}" x1="${center.x}" y1="${center.y}" x2="${node.x}" y2="${node.y}"/>`).join('');
  const labels = nodes.map((node) => `<g class="detail-node"><circle cx="${node.x}" cy="${node.y}" r="19" fill="${node.relation === 'dependency' ? '#187a70' : '#ee8352'}"/><text x="${node.x}" y="${node.y + 4}" text-anchor="middle">${esc(node.name)}</text></g>`).join('');
  const dependencyLabel = dependencies.length ? 'DEPENDS ON' : 'NO DEPENDENCIES';
  const dependentLabel = dependents.length ? 'USED BY' : 'NO DEPENDENTS';
  document.querySelector('#detail-graph').innerHTML = `<svg width="${width * graphZoom}" height="${height * graphZoom}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Selected extension relationships"><text class="side-label" x="18" y="16">${dependencyLabel}</text><text class="side-label" x="${width - 18}" y="16" text-anchor="end">${dependentLabel}</text>${lines}<circle class="detail-center" cx="${center.x}" cy="${center.y}" r="28"/><text class="graph-label" x="${center.x}" y="${center.y + 4}" text-anchor="middle">${esc(extension.name)}</text>${labels}</svg>`;
  document.querySelector('#detail-graph svg').addEventListener('wheel', (event) => {
    event.preventDefault();
    graphZoom = Math.max(.5, Math.min(3, graphZoom + (event.deltaY < 0 ? .15 : -.15)));
    renderDetailGraph(extension, dependencies, dependents);
  }, {passive: false});
}

document.querySelectorAll('#types button').forEach((button) => button.addEventListener('click', () => { document.querySelector('#types .active').classList.remove('active'); button.classList.add('active'); type = button.dataset.type; loadExtensions(); }));
search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(loadExtensions, 180); });
loadSummary();
loadExtensions();
