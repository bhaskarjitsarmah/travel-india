const MONTHS = ["", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

// ---------- LocalStorage state ----------
const LS_VISITED = "itr_visited";
const LS_WISHLIST = "itr_wishlist";

function loadSet(key) {
  try {
    return new Set(JSON.parse(localStorage.getItem(key) || "[]"));
  } catch { return new Set(); }
}
function saveSet(key, set) {
  localStorage.setItem(key, JSON.stringify([...set]));
}

const state = {
  places: [],
  placesById: {},
  visitedIds: loadSet(LS_VISITED),
  wishlistIds: loadSet(LS_WISHLIST),
  currentMonth: new Date().getMonth() + 1,
  weatherEnabled: false,
};

// ---------- Tabs ----------
document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".view").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById(t.dataset.tab).classList.add("active");
    if (t.dataset.tab === "browse") renderBrowse();
    if (t.dataset.tab === "visited") renderVisited();
    if (t.dataset.tab === "map") renderMap();
    if (t.dataset.tab === "festivals") renderFestivals();
    if (t.dataset.tab === "stats") renderStats();
    if (t.dataset.tab === "plan") initPlanTab();
  });
});

// ---------- Init ----------
async function init() {
  const monthSelect = document.getElementById("monthSelect");
  for (let i = 1; i <= 12; i++) {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = MONTHS[i];
    monthSelect.appendChild(opt);
  }
  monthSelect.value = state.currentMonth;

  await loadPlaces();
  await loadRecommendations();
}

async function loadPlaces() {
  const r = await fetch("/api/places");
  const data = await r.json();
  state.places = data.places;
  state.placesById = Object.fromEntries(data.places.map(p => [p.id, p]));
  state.weatherEnabled = data.weather_enabled;
  document.getElementById("totalCount").textContent = data.count;
  document.getElementById("visitedCount").textContent = state.visitedIds.size;
  document.getElementById("wishlistCount").textContent = state.wishlistIds.size;
  document.getElementById("monthBadge").textContent = MONTHS[data.current_month];
  document.getElementById("weatherBadge").textContent =
    "weather: " + (data.weather_enabled ? "live" : "off");
}

// ---------- Recommendations ----------
document.getElementById("refreshBtn").addEventListener("click", loadRecommendations);

async function loadRecommendations() {
  const loader = document.getElementById("loader");
  const grid = document.getElementById("recommendGrid");
  loader.classList.remove("hidden");
  grid.innerHTML = "";

  const body = {
    top_n: parseInt(document.getElementById("topN").value, 10),
    use_weather: document.getElementById("useWeather").checked,
    month: parseInt(document.getElementById("monthSelect").value, 10),
    region: document.getElementById("regionSelect").value || null,
    place_type: document.getElementById("typeSelect").value || null,
    exclude_ids: [...state.visitedIds],
  };

  try {
    const r = await fetch("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    loader.classList.add("hidden");
    grid.innerHTML = "";
    if (!data.recommendations.length) {
      grid.innerHTML = `<div class="empty">No matches. Try clearing filters or marking fewer places as visited.</div>`;
      return;
    }
    data.recommendations.forEach((p, i) => grid.appendChild(renderCard(p, i + 1)));
  } catch (e) {
    loader.classList.add("hidden");
    grid.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
  }
}

// ---------- Browse ----------
document.getElementById("searchInput").addEventListener("input", renderBrowse);
document.getElementById("browseRegion").addEventListener("change", renderBrowse);
document.getElementById("browseVisited").addEventListener("change", renderBrowse);

function renderBrowse() {
  const q = document.getElementById("searchInput").value.toLowerCase().trim();
  const region = document.getElementById("browseRegion").value;
  const filter = document.getElementById("browseVisited").value;
  const grid = document.getElementById("browseGrid");

  let filtered = state.places.slice();
  if (region) filtered = filtered.filter(p => p.region === region);
  if (filter === "visited") filtered = filtered.filter(p => state.visitedIds.has(p.id));
  if (filter === "unvisited") filtered = filtered.filter(p => !state.visitedIds.has(p.id));
  if (q) {
    filtered = filtered.filter(p =>
      p.name.toLowerCase().includes(q) ||
      (p.state || "").toLowerCase().includes(q) ||
      (p.type || []).some(t => t.toLowerCase().includes(q)) ||
      (p.description || "").toLowerCase().includes(q)
    );
  }

  filtered.sort((a, b) => (b.must_see_score || 0) - (a.must_see_score || 0));

  grid.innerHTML = "";
  if (!filtered.length) {
    grid.innerHTML = `<div class="empty">No places match these filters.</div>`;
    return;
  }
  filtered.forEach(p => grid.appendChild(renderCard(p)));
}

function renderVisited() {
  const grid = document.getElementById("visitedGrid");
  const empty = document.getElementById("visitedEmpty");
  const filter = document.getElementById("visitedFilter").value;

  let items;
  if (filter === "visited") {
    items = state.places.filter(p => state.visitedIds.has(p.id));
  } else if (filter === "wishlist") {
    items = state.places.filter(p => state.wishlistIds.has(p.id));
  } else {
    items = state.places.filter(p => state.visitedIds.has(p.id) || state.wishlistIds.has(p.id));
  }

  grid.innerHTML = "";
  if (!items.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");
  items.forEach(p => grid.appendChild(renderCard(p)));
}

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "visitedFilter") renderVisited();
});

// ---------- Card renderer ----------
function renderCard(p, rank = null) {
  const isVisited = state.visitedIds.has(p.id);
  const isWishlist = state.wishlistIds.has(p.id);
  const card = document.createElement("div");
  card.className = "card" + (isVisited ? " visited" : "") + (isWishlist ? " wishlisted" : "");

  const tags = (p.type || []).map(t => `<span class="tag">${t}</span>`).join("");
  const months = (p.best_months || []).map(m => MONTHS[m].slice(0, 3)).join(", ") || "Any";

  let scoreBlock = "";
  if (p.scoring) {
    const s = p.scoring;
    const weatherCell = s.weather !== null && s.weather !== undefined
      ? `<span>Weather<b>${(s.weather * 100).toFixed(0)}%</b></span>`
      : `<span>Weather<b>—</b></span>`;
    scoreBlock = `
      <div class="score-row">
        <div class="score-breakdown">
          <span>Season<b>${(s.season * 100).toFixed(0)}%</b></span>
          <span>Must-see<b>${(s.must_see * 5).toFixed(1)}</b></span>
          <span>Access<b>${(s.access * 5).toFixed(1)}</b></span>
          ${weatherCell}
        </div>
        <div class="total">${(s.score * 100).toFixed(0)}</div>
      </div>`;
  }

  const visitBtn = isVisited
    ? `<button class="visit-btn visited" data-id="${p.id}" data-action="unvisit">✓ Visited</button>`
    : `<button class="visit-btn" data-id="${p.id}" data-action="visit">Mark visited</button>`;

  const wishBtn = isWishlist
    ? `<button class="wish-btn active" data-id="${p.id}" data-action="unwish">★ Wishlist</button>`
    : `<button class="wish-btn" data-id="${p.id}" data-action="wish">☆ Wishlist</button>`;

  const deleteBtn = p.custom
    ? `<button class="delete-btn" data-id="${p.id}" data-action="delete">Del</button>`
    : "";

  const imgUrl = p.thumb_url || p.image_url;
  const photo = imgUrl
    ? `<div class="card-photo" style="background-image:url('${imgUrl}')"></div>`
    : `<div class="card-photo placeholder" data-id="${p.id}"></div>`;

  card.innerHTML = `
    ${rank ? `<div class="rank-badge">#${rank}</div>` : ""}
    ${photo}
    <h3>${p.name}</h3>
    <div class="location">
      <span class="tag region">${p.region}</span>
      ${p.state}${p.city && p.city !== p.state ? ` · ${p.city}` : ""}
    </div>
    <div class="tags">${tags}</div>
    <div class="desc">${p.description || ""}</div>
    <div class="weather-chip">Best: ${months} · ${p.duration_days || 1}d · Access ${p.accessibility}/5</div>
    ${scoreBlock}
    <div class="actions">
      ${visitBtn}
      ${wishBtn}
      <button data-id="${p.id}" data-action="map">Map</button>
      ${deleteBtn}
    </div>
  `;

  card.querySelectorAll("button[data-action]").forEach(btn => {
    btn.addEventListener("click", (e) => handleAction(e, p));
  });

  // Lazy-fetch photo if missing
  if (!imgUrl) {
    lazyFetchPhoto(p.id, card);
  }
  return card;
}

const _photoPromise = new Map();
async function lazyFetchPhoto(id, card) {
  if (_photoPromise.has(id)) {
    _photoPromise.get(id).then(url => applyPhoto(card, url));
    return;
  }
  const promise = fetch(`/api/photo/${id}`)
    .then(r => r.ok ? r.json() : null)
    .then(j => j ? (j.thumb_url || j.image_url) : null)
    .catch(() => null);
  _photoPromise.set(id, promise);
  const url = await promise;
  if (url) {
    // update state so subsequent renders have it
    if (state.placesById[id]) state.placesById[id].thumb_url = url;
    applyPhoto(card, url);
  }
}
function applyPhoto(card, url) {
  const el = card.querySelector(".card-photo");
  if (!el) return;
  el.style.backgroundImage = `url('${url}')`;
  el.classList.remove("placeholder");
}

async function handleAction(e, place) {
  const action = e.target.dataset.action;
  const id = e.target.dataset.id;

  if (action === "visit" || action === "unvisit") {
    const visited = action === "visit";
    if (visited) state.visitedIds.add(id);
    else state.visitedIds.delete(id);
    saveSet(LS_VISITED, state.visitedIds);
    document.getElementById("visitedCount").textContent = state.visitedIds.size;
    refreshCurrentView();
  }

  if (action === "wish" || action === "unwish") {
    const on = action === "wish";
    if (on) state.wishlistIds.add(id);
    else state.wishlistIds.delete(id);
    saveSet(LS_WISHLIST, state.wishlistIds);
    document.getElementById("wishlistCount").textContent = state.wishlistIds.size;
    refreshCurrentView();
  }

  if (action === "map") {
    window.open(`https://www.google.com/maps/search/?api=1&query=${place.lat},${place.lon}`, "_blank");
  }

  if (action === "delete") {
    if (!confirm(`Delete ${place.name}?`)) return;
    await fetch(`/api/places/${id}`, { method: "DELETE" });
    await loadPlaces();
    renderBrowse();
  }
}

function refreshCurrentView() {
  const activeTab = document.querySelector(".tab.active").dataset.tab;
  if (activeTab === "recommend") loadRecommendations();
  else if (activeTab === "browse") renderBrowse();
  else if (activeTab === "visited") renderVisited();
  else if (activeTab === "map") renderMap();
  else if (activeTab === "stats") renderStats();
}

// ---------- Map ----------
let _map = null;
let _markerLayer = null;
const INDIA_BOUNDS = L.latLngBounds([6.5, 67.5], [37.5, 97.5]);

async function loadIndiaMask(map) {
  try {
    const r = await fetch("/data/india.geojson");
    const gj = await r.json();
    const geom = gj.features[0].geometry;
    const polys = geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates];

    const indiaRings = [];
    polys.forEach(poly => {
      // poly[0] is the outer ring; ignore holes inside India for simplicity
      const ring = poly[0].map(([lng, lat]) => [lat, lng]);
      indiaRings.push(ring);
    });

    // Outline India
    L.polygon(indiaRings, {
      color: "#ff7a45",
      weight: 1.5,
      fill: false,
      interactive: false,
    }).addTo(map);

    // Mask: world rectangle with India polygons as holes
    const worldRect = [
      [-85, -180], [-85, 180], [85, 180], [85, -180]
    ];
    L.polygon([worldRect, ...indiaRings], {
      stroke: false,
      fillColor: "#0a0d14",
      fillOpacity: 0.96,
      interactive: false,
    }).addTo(map);
  } catch (e) {
    console.warn("India outline failed to load:", e);
  }
}

function ensureMap() {
  if (_map) return _map;
  _map = L.map("mapContainer", {
    center: [22.5, 80],
    zoom: 5,
    minZoom: 4,
    maxZoom: 12,
    maxBounds: INDIA_BOUNDS,
    maxBoundsViscosity: 1.0,
    zoomControl: true,
    worldCopyJump: false,
  });
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
    maxZoom: 12,
    bounds: INDIA_BOUNDS,
    noWrap: true,
  }).addTo(_map);
  loadIndiaMask(_map);
  _markerLayer = L.layerGroup().addTo(_map);
  _map.fitBounds(INDIA_BOUNDS);
  return _map;
}

const visitedIcon = () => L.divIcon({
  className: "leaflet-pin pin-visited",
  html: "✓",
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

const wishlistIcon = () => L.divIcon({
  className: "leaflet-pin pin-wishlist",
  html: "★",
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

const unvisitedIcon = () => L.divIcon({
  className: "leaflet-pin pin-unvisited",
  html: "•",
  iconSize: [12, 12],
  iconAnchor: [6, 6],
});

function renderMap() {
  ensureMap();
  setTimeout(() => _map.invalidateSize(), 50);
  _markerLayer.clearLayers();

  const showUnvisited = document.getElementById("showUnvisited").checked;
  const visited = state.places.filter(p => state.visitedIds.has(p.id));
  const wishlist = state.places.filter(p => !state.visitedIds.has(p.id) && state.wishlistIds.has(p.id));
  const other = state.places.filter(p => !state.visitedIds.has(p.id) && !state.wishlistIds.has(p.id));

  document.getElementById("mapVisitedCount").textContent = visited.length;
  document.getElementById("mapUnvisitedCount").textContent = other.length + wishlist.length;

  if (showUnvisited) {
    other.forEach(p => {
      L.marker([p.lat, p.lon], { icon: unvisitedIcon(), opacity: 0.65 })
        .bindPopup(popupHtml(p, false))
        .addTo(_markerLayer);
    });
  }
  wishlist.forEach(p => {
    L.marker([p.lat, p.lon], { icon: wishlistIcon() })
      .bindPopup(popupHtml(p, false))
      .addTo(_markerLayer);
  });
  visited.forEach(p => {
    L.marker([p.lat, p.lon], { icon: visitedIcon() })
      .bindPopup(popupHtml(p, true))
      .addTo(_markerLayer);
  });

  if (visited.length > 0) {
    const bounds = L.latLngBounds(visited.map(p => [p.lat, p.lon]));
    _map.fitBounds(bounds, { padding: [40, 40], maxZoom: 7 });
  } else {
    _map.fitBounds(INDIA_BOUNDS);
  }
}

function popupHtml(p, isVisited) {
  const isWish = state.wishlistIds.has(p.id);
  const img = p.thumb_url || p.image_url;
  const imgEl = img ? `<img class="pop-img" src="${img}" alt="" />` : "";
  return `
    <div class="pop">
      ${imgEl}
      <strong>${p.name}</strong>
      <div class="pop-loc">${p.state}${p.city && p.city !== p.state ? ' · ' + p.city : ''}</div>
      <div class="pop-types">${(p.type || []).join(', ')}</div>
      <div class="pop-desc">${p.description || ''}</div>
      <div class="pop-actions">
        <button class="pop-btn" onclick="togglePinVisited('${p.id}', ${!isVisited})">
          ${isVisited ? '✓ Visited — Unmark' : 'Mark visited'}
        </button>
        <button class="pop-btn wish" onclick="togglePinWish('${p.id}', ${!isWish})">
          ${isWish ? '★ Wishlisted' : '☆ Wishlist'}
        </button>
      </div>
    </div>
  `;
}

window.togglePinVisited = function (id, makeVisited) {
  if (makeVisited) state.visitedIds.add(id);
  else state.visitedIds.delete(id);
  saveSet(LS_VISITED, state.visitedIds);
  document.getElementById("visitedCount").textContent = state.visitedIds.size;
  renderMap();
};

window.togglePinWish = function (id, makeWish) {
  if (makeWish) state.wishlistIds.add(id);
  else state.wishlistIds.delete(id);
  saveSet(LS_WISHLIST, state.wishlistIds);
  document.getElementById("wishlistCount").textContent = state.wishlistIds.size;
  renderMap();
};

document.getElementById("showUnvisited").addEventListener("change", renderMap);
document.getElementById("fitAllBtn").addEventListener("click", () => {
  if (!_map) return;
  _map.fitBounds(INDIA_BOUNDS);
});

// ---------- Stats tab (computed client-side from localStorage) ----------
function computeStats() {
  const places = state.places;
  const visited = places.filter(p => state.visitedIds.has(p.id));
  const total = places.length;
  const statesVisited = new Set(visited.map(p => p.state));
  const statesTotal = new Set(places.map(p => p.state));

  const regionTotals = {};
  const regionVisited = {};
  const typeTotals = {};
  const typeVisited = {};
  const stateBreakdown = {};

  for (const p of places) {
    regionTotals[p.region] = (regionTotals[p.region] || 0) + 1;
    if (state.visitedIds.has(p.id)) {
      regionVisited[p.region] = (regionVisited[p.region] || 0) + 1;
    }
    for (const t of (p.type || [])) {
      typeTotals[t] = (typeTotals[t] || 0) + 1;
      if (state.visitedIds.has(p.id)) {
        typeVisited[t] = (typeVisited[t] || 0) + 1;
      }
    }
    if (!stateBreakdown[p.state]) stateBreakdown[p.state] = { visited: 0, total: 0 };
    stateBreakdown[p.state].total++;
    if (state.visitedIds.has(p.id)) stateBreakdown[p.state].visited++;
  }

  const mustSeeVisited = visited.filter(p => (p.must_see_score || 0) >= 5).length;
  const mustSeeTotal = places.filter(p => (p.must_see_score || 0) >= 5).length;

  const regionsList = Object.keys(regionTotals).sort().map(r => ({
    region: r,
    visited: regionVisited[r] || 0,
    total: regionTotals[r],
    percentage: Math.round((regionVisited[r] || 0) / regionTotals[r] * 100),
  }));

  const typesList = Object.keys(typeTotals)
    .sort((a, b) => typeTotals[b] - typeTotals[a])
    .map(t => ({
      type: t,
      visited: typeVisited[t] || 0,
      total: typeTotals[t],
      percentage: Math.round((typeVisited[t] || 0) / typeTotals[t] * 100),
    }));

  const stateList = Object.entries(stateBreakdown)
    .map(([s, v]) => ({
      state: s, ...v,
      percentage: Math.round(v.visited / v.total * 100),
    }))
    .sort((a, b) => b.visited - a.visited || a.state.localeCompare(b.state));

  return {
    visited_count: visited.length,
    total_count: total,
    percentage: total ? Math.round(visited.length / total * 1000) / 10 : 0,
    wishlist_count: state.wishlistIds.size,
    states_visited_count: statesVisited.size,
    states_total_count: statesTotal.size,
    regions: regionsList,
    types: typesList,
    state_breakdown: stateList,
    must_see: {
      visited: mustSeeVisited,
      total: mustSeeTotal,
      percentage: mustSeeTotal ? Math.round(mustSeeVisited / mustSeeTotal * 100) : 0,
    },
  };
}

function renderStats() {
  const el = document.getElementById("statsContent");
  const d = computeStats();

  const bar = (val, total, pct) =>
    `<div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
     <span class="bar-label">${val}/${total} <b>${pct}%</b></span>`;

  const regionRows = d.regions.map(r =>
    `<tr><td>${r.region}</td><td>${bar(r.visited, r.total, r.percentage)}</td></tr>`).join("");

  const typeRows = d.types.map(t =>
    `<tr><td>${t.type}</td><td>${bar(t.visited, t.total, t.percentage)}</td></tr>`).join("");

  const topStates = d.state_breakdown.filter(s => s.visited > 0).slice(0, 12).map(s =>
    `<tr><td>${s.state}</td><td>${bar(s.visited, s.total, s.percentage)}</td></tr>`).join("")
    || `<tr><td colspan="2" class="muted">No states visited yet.</td></tr>`;

  el.innerHTML = `
    <div class="stats-actions">
      <button id="exportBtn">Export my data</button>
      <button id="importBtn">Import data</button>
      <button id="clearBtn" class="delete-btn">Clear all</button>
    </div>
    <div class="stat-hero">
      <div class="big-stat">
        <div class="big-num">${d.percentage}%</div>
        <div class="big-label">of India explored</div>
        <div class="muted">${d.visited_count} of ${d.total_count} places</div>
      </div>
      <div class="big-stat">
        <div class="big-num">${d.states_visited_count}</div>
        <div class="big-label">states visited</div>
        <div class="muted">out of ${d.states_total_count} total</div>
      </div>
      <div class="big-stat">
        <div class="big-num">${d.must_see.visited}/${d.must_see.total}</div>
        <div class="big-label">must-see seen</div>
        <div class="muted">${d.must_see.percentage}% of the iconic sites</div>
      </div>
      <div class="big-stat">
        <div class="big-num">${d.wishlist_count}</div>
        <div class="big-label">on wishlist</div>
        <div class="muted">queued for the future</div>
      </div>
    </div>

    <div class="stats-section">
      <h3>Coverage by region</h3>
      <table class="stats-table">${regionRows}</table>
    </div>
    <div class="stats-section">
      <h3>Coverage by type</h3>
      <table class="stats-table">${typeRows}</table>
    </div>
    <div class="stats-section">
      <h3>Top states by visits</h3>
      <table class="stats-table">${topStates}</table>
    </div>
  `;
  document.getElementById("exportBtn").addEventListener("click", exportData);
  document.getElementById("importBtn").addEventListener("click", importData);
  document.getElementById("clearBtn").addEventListener("click", clearData);
}

function exportData() {
  const blob = new Blob([JSON.stringify({
    visited: [...state.visitedIds],
    wishlist: [...state.wishlistIds],
    exported_at: new Date().toISOString(),
  }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `india-travels-${new Date().toISOString().split('T')[0]}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function importData() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "application/json";
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      if (!Array.isArray(data.visited) || !Array.isArray(data.wishlist)) {
        alert("Invalid file format");
        return;
      }
      state.visitedIds = new Set(data.visited);
      state.wishlistIds = new Set(data.wishlist);
      saveSet(LS_VISITED, state.visitedIds);
      saveSet(LS_WISHLIST, state.wishlistIds);
      document.getElementById("visitedCount").textContent = state.visitedIds.size;
      document.getElementById("wishlistCount").textContent = state.wishlistIds.size;
      renderStats();
      alert(`Imported ${data.visited.length} visited and ${data.wishlist.length} wishlist places.`);
    } catch (err) {
      alert("Import failed: " + err.message);
    }
  };
  input.click();
}

function clearData() {
  if (!confirm("Erase all visited + wishlist data on this browser? (Use Export first if you want a backup.)")) return;
  state.visitedIds.clear();
  state.wishlistIds.clear();
  saveSet(LS_VISITED, state.visitedIds);
  saveSet(LS_WISHLIST, state.wishlistIds);
  document.getElementById("visitedCount").textContent = 0;
  document.getElementById("wishlistCount").textContent = 0;
  renderStats();
}

// ---------- Festivals tab ----------
function initFestivalsControls() {
  const sel = document.getElementById("festMonth");
  if (sel.options.length > 1) return;
  for (let i = 1; i <= 12; i++) {
    const opt = document.createElement("option");
    opt.value = i;
    opt.textContent = MONTHS[i];
    sel.appendChild(opt);
  }
  sel.value = String(state.currentMonth);
  sel.addEventListener("change", renderFestivals);
}

async function renderFestivals() {
  initFestivalsControls();
  const month = parseInt(document.getElementById("festMonth").value, 10);
  const url = month ? `/api/festivals?month=${month}` : "/api/festivals";
  const r = await fetch(url);
  const d = await r.json();
  const list = document.getElementById("festivalList");
  list.innerHTML = "";
  if (!d.festivals.length) {
    list.innerHTML = `<div class="empty">No festivals tagged for this month.</div>`;
    return;
  }
  d.festivals.forEach(f => {
    const places = f.place_ids.map(pid => {
      const p = state.placesById[pid];
      return p ? `<a class="fest-place" data-id="${pid}">${p.name}</a>` : pid;
    }).join(", ");

    const card = document.createElement("div");
    card.className = "festival-card fest-" + f.type;
    card.innerHTML = `
      <div class="fest-type-badge">${f.type}</div>
      <h3>${f.name}</h3>
      <div class="fest-dates">${f.dates}</div>
      <p class="fest-desc">${f.description}</p>
      <div class="fest-places">At: ${places}</div>
    `;
    list.appendChild(card);
  });

  list.querySelectorAll(".fest-place").forEach(a => {
    a.addEventListener("click", (e) => {
      const pid = e.target.dataset.id;
      const place = state.placesById[pid];
      if (!place) return;
      window.open(`https://www.google.com/maps/search/?api=1&query=${place.lat},${place.lon}`, "_blank");
    });
  });
}

// ---------- Plan Trip tab ----------
function initPlanTab() {
  const sel = document.getElementById("planMonth");
  if (sel.options.length === 0) {
    for (let i = 1; i <= 12; i++) {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = MONTHS[i];
      sel.appendChild(opt);
    }
    sel.value = state.currentMonth;
  }
}

document.getElementById("planForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const citySel = document.getElementById("planCity");
  const opt = citySel.options[citySel.selectedIndex];
  const payload = {
    start_city: citySel.value,
    start_lat: parseFloat(opt.dataset.lat),
    start_lon: parseFloat(opt.dataset.lon),
    days: parseInt(document.getElementById("planDays").value, 10),
    month: parseInt(document.getElementById("planMonth").value, 10),
    interests: document.getElementById("planInterests").value
      .split(",").map(x => x.trim()).filter(Boolean),
    exclude_ids: document.getElementById("planExcludeVisited").checked
      ? [...state.visitedIds] : [],
    include_only_ids: document.getElementById("planOnlyWishlist").checked
      ? [...state.wishlistIds] : null,
  };

  const loader = document.getElementById("planLoader");
  const result = document.getElementById("planResult");
  result.innerHTML = "";
  loader.classList.remove("hidden");

  try {
    const r = await fetch("/api/itinerary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    loader.classList.add("hidden");

    if (d.error) {
      result.innerHTML = `<div class="empty">Couldn't plan: ${d.error}</div>`;
      return;
    }

    const daysHtml = (d.days || []).map(day => {
      const place = state.placesById[day.place_id];
      const img = place && (place.thumb_url || place.image_url);
      const photo = img ? `<div class="plan-day-photo" style="background-image:url('${img}')"></div>` : "";
      const travel = day.travel ? `<div class="plan-travel">→ ${day.travel}</div>` : "";
      const placeName = place ? place.name : day.place_id;
      const placeMeta = place ? `${place.state} · ${(place.type || []).join(", ")}` : "";
      return `
        <div class="plan-day">
          <div class="plan-day-num">Day ${day.day}</div>
          ${photo}
          <div class="plan-day-body">
            <h4>${day.title}</h4>
            <div class="plan-place">${placeName}</div>
            <div class="muted">${placeMeta}</div>
            <p class="plan-notes">${day.notes || ""}</p>
            ${travel}
          </div>
        </div>
      `;
    }).join("");

    result.innerHTML = `
      <div class="plan-summary">
        <h3>Your ${d.total_days}-day plan</h3>
        <p>${d.summary || ""}</p>
        <div class="muted">Estimated ${d.estimated_distance_km || "?"}km total</div>
      </div>
      <div class="plan-timeline">${daysHtml}</div>
    `;
  } catch (err) {
    loader.classList.add("hidden");
    result.innerHTML = `<div class="empty">Error: ${err.message}</div>`;
  }
});

// ---------- NL Search ----------
document.getElementById("askBtn").addEventListener("click", runAsk);
document.getElementById("askInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runAsk();
});
document.querySelectorAll(".example-chip").forEach(b => {
  b.addEventListener("click", () => {
    document.getElementById("askInput").value = b.dataset.q;
    runAsk();
  });
});

async function runAsk() {
  const query = document.getElementById("askInput").value.trim();
  const errEl = document.getElementById("askError");
  const grid = document.getElementById("askGrid");
  const loader = document.getElementById("askLoader");
  const chipsEl = document.getElementById("filterChips");
  errEl.textContent = "";
  errEl.className = "status";
  chipsEl.innerHTML = "";
  grid.innerHTML = "";

  if (!query) {
    errEl.className = "status error";
    errEl.textContent = "Type a question first.";
    return;
  }

  loader.classList.remove("hidden");
  try {
    const r = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        use_weather: document.getElementById("askWeather").checked,
        exclude_ids: [...state.visitedIds],
      }),
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    loader.classList.add("hidden");

    renderFilterChips(data.filters, chipsEl);

    if (!data.results.length) {
      grid.innerHTML = `<div class="empty">No places matched. Try a broader query or remove filters from chips above.</div>`;
      return;
    }
    data.results.forEach((p, i) => grid.appendChild(renderCard(p, i + 1)));
  } catch (e) {
    loader.classList.add("hidden");
    errEl.className = "status error";
    errEl.textContent = "Error: " + e.message;
  }
}

function renderFilterChips(filters, container) {
  if (!filters) return;
  const isFallback = filters._source === "fallback";
  const errMsg = filters._llm_error;
  const order = [
    ["regions", "Region"],
    ["states", "State"],
    ["types", "Type"],
    ["months", "Month"],
    ["min_accessibility", "Min access"],
    ["max_accessibility", "Max access"],
    ["min_must_see", "Min must-see"],
    ["keywords", "Keywords"],
  ];
  const chips = [];
  for (const [key, label] of order) {
    const v = filters[key];
    if (v === null || v === undefined) continue;
    if (Array.isArray(v) && v.length === 0) continue;
    let display = v;
    if (key === "months" && Array.isArray(v)) {
      display = v.map(m => MONTHS[m]).join(", ");
    } else if (Array.isArray(v)) {
      display = v.join(", ");
    }
    chips.push(`<span class="filter-chip${isFallback ? ' fallback' : ''}">${label}<b>${display}</b></span>`);
  }
  if (chips.length === 0) {
    container.innerHTML = `<span class="filter-chip fallback">No filters extracted — showing all unvisited</span>`;
  } else {
    container.innerHTML = chips.join("");
  }
  if (isFallback) {
    container.innerHTML += `<span class="filter-chip fallback">⚠ Used offline parser${errMsg ? ` (${errMsg.slice(0,80)})` : ''}</span>`;
  }
}

// ---------- Add form ----------
document.getElementById("addForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const data = Object.fromEntries(fd.entries());
  const status = document.getElementById("addStatus");
  status.className = "status";
  status.textContent = "";

  const parseList = (s, fn = x => x) =>
    s ? s.split(",").map(x => fn(x.trim())).filter(Boolean) : [];

  const payload = {
    id: data.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
    name: data.name,
    state: data.state,
    region: data.region,
    city: data.city || null,
    lat: parseFloat(data.lat),
    lon: parseFloat(data.lon),
    type: parseList(data.type),
    best_months: parseList(data.best_months, x => parseInt(x)).filter(n => n >= 1 && n <= 12),
    ideal_temp_min: data.ideal_temp_min ? parseFloat(data.ideal_temp_min) : null,
    ideal_temp_max: data.ideal_temp_max ? parseFloat(data.ideal_temp_max) : null,
    accessibility: parseInt(data.accessibility) || 3,
    must_see_score: parseInt(data.must_see_score) || 3,
    duration_days: parseInt(data.duration_days) || 1,
    description: data.description || "",
  };

  try {
    const r = await fetch("/api/places", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(await r.text());
    status.className = "status success";
    status.textContent = `Added ${payload.name}.`;
    e.target.reset();
    await loadPlaces();
  } catch (err) {
    status.className = "status error";
    status.textContent = "Error: " + err.message;
  }
});

init();
