const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

// House filter ('LS' | 'RS' | null), set by components/HouseToggle.jsx.
// Only the seven dataset-wide calls below take it, and only when one house
// is selected. With none selected every URL is exactly what it was before.
let currentHouse = null;

export function setApiHouse(house) {
  currentHouse = house === 'LS' || house === 'RS' ? house : null;
}

function houseQs() {
  return currentHouse ? `?house=${currentHouse}` : '';
}

function addHouse(query) {
  if (currentHouse) query.set('house', currentHouse);
  return query;
}

// A failed call throws an Error that carries the HTTP status (`status`),
// so pages can tell "that record doesn't exist" (404) apart from "the data
// failed to load" (5xx, network) and show the right state for each.
function apiError(res, message) {
  const err = new Error(`${message} (HTTP ${res.status})`);
  err.status = res.status;
  return err;
}

export function isNotFound(err) {
  return err != null && err.status === 404;
}

export async function getSummary() {
  const res = await fetch(`${API_BASE}/summary${houseQs()}`);
  if (!res.ok) throw apiError(res, 'Failed to get summary');
  return res.json();
}

export async function getQueue(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      query.set(k, v);
    }
  });
  const res = await fetch(`${API_BASE}/queue?${addHouse(query)}`);
  if (!res.ok) throw apiError(res, 'Failed to get queue');
  return res.json();
}

export async function getRecordDetail(recordId) {
  const res = await fetch(`${API_BASE}/record/${encodeURIComponent(recordId)}`);
  if (!res.ok) throw apiError(res, 'Failed to get record detail');
  return res.json();
}

export async function getAnalytics() {
  const res = await fetch(`${API_BASE}/analytics${houseQs()}`);
  if (!res.ok) throw apiError(res, 'Failed to get analytics');
  return res.json();
}

export async function getDataHealth() {
  const res = await fetch(`${API_BASE}/data-health`);
  if (!res.ok) throw apiError(res, 'Failed to get data health');
  return res.json();
}

export async function getStages() {
  const res = await fetch(`${API_BASE}/stages`);
  if (!res.ok) throw apiError(res, 'Failed to get stages');
  return res.json();
}

export async function getConstituencies() {
  const res = await fetch(`${API_BASE}/constituencies`);
  if (!res.ok) throw apiError(res, 'Failed to get constituencies');
  return res.json();
}

export async function getStates() {
  const res = await fetch(`${API_BASE}/states`);
  if (!res.ok) throw apiError(res, 'Failed to get states');
  return res.json();
}

export async function getMapData(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      query.set(k, v);
    }
  });
  const qs = addHouse(query).toString();
  const res = await fetch(`${API_BASE}/map-data${qs ? '?' + qs : ''}`);
  if (!res.ok) throw apiError(res, 'Failed to get map data');
  return res.json();
}

export async function getMapWorks(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      query.set(k, v);
    }
  });
  const res = await fetch(`${API_BASE}/map-works?${addHouse(query)}`);
  if (!res.ok) throw apiError(res, 'Failed to get map works');
  return res.json();
}

export async function getMapFilters() {
  const res = await fetch(`${API_BASE}/map-filters${houseQs()}`);
  if (!res.ok) throw apiError(res, 'Failed to get map filters');
  return res.json();
}

export async function getGraphData() {
  const res = await fetch(`${API_BASE}/graph-data${houseQs()}`);
  if (!res.ok) throw apiError(res, 'Failed to get graph data');
  return res.json();
}

export async function investigateRecord(recordId, data = {}) {
  const res = await fetch(`${API_BASE}/investigate/${encodeURIComponent(recordId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw apiError(res, 'Failed to investigate record');
  return res.json();
}

export async function getAuditTrail() {
  const res = await fetch(`${API_BASE}/audit-trail`);
  if (!res.ok) throw apiError(res, 'Failed to get audit trail');
  return res.json();
}

export async function getMps() {
  const res = await fetch(`${API_BASE}/mps`);
  if (!res.ok) throw apiError(res, 'Failed to get MPs');
  return res.json();
}

export async function getMpPerformance(mpName) {
  const res = await fetch(`${API_BASE}/mp-performance/${encodeURIComponent(mpName)}`);
  if (!res.ok) throw apiError(res, 'Failed to get MP performance');
  return res.json();
}

export async function getConstituencyPerformance(constituencyName) {
  const res = await fetch(`${API_BASE}/constituency-performance/${encodeURIComponent(constituencyName)}`);
  if (!res.ok) throw apiError(res, 'Failed to get constituency performance');
  return res.json();
}

export async function getMpComparison(mpNames) {
  const res = await fetch(`${API_BASE}/mp-comparison?mps=${encodeURIComponent(mpNames.join(','))}`);
  if (!res.ok) throw apiError(res, 'Failed to get MP comparison');
  return res.json();
}

export async function getConstituencyComparison(constituencyNames) {
  const res = await fetch(`${API_BASE}/constituency-comparison?constituencies=${encodeURIComponent(constituencyNames.join(','))}`);
  if (!res.ok) throw apiError(res, 'Failed to get constituency comparison');
  return res.json();
}

export async function getChatStatus() {
  const res = await fetch(`${API_BASE}/chat/status`);
  if (!res.ok) throw apiError(res, 'Failed to get chat status');
  return res.json();
}

export async function sendChatMessage(message, history = []) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) throw apiError(res, 'Failed to reach the help assistant');
  return res.json();
}

// ── New v2.0 endpoints ──────────────────────────────────────────

export async function getGeoJSON() {
  const res = await fetch(`${API_BASE}/geojson`);
  if (!res.ok) throw apiError(res, 'Failed to get GeoJSON');
  return res.json();
}

export async function getGeographicCoverage() {
  const res = await fetch(`${API_BASE}/geographic-coverage`);
  if (!res.ok) throw apiError(res, 'Failed to get geographic coverage');
  return res.json();
}

export async function getConstituencyIntelligence(state, constituency) {
  const params = new URLSearchParams({ state, constituency });
  const res = await fetch(`${API_BASE}/constituency-intelligence?${params}`);
  if (!res.ok) throw apiError(res, 'Failed to get constituency intelligence');
  return res.json();
}

export async function getRiskDetail(projectId) {
  const res = await fetch(`${API_BASE}/risk/${encodeURIComponent(projectId)}`);
  if (!res.ok) throw apiError(res, 'Failed to get risk detail');
  return res.json();
}

export async function getRiskTop(limit = 20) {
  const res = await fetch(`${API_BASE}/risk/top?limit=${limit}`);
  if (!res.ok) throw apiError(res, 'Failed to get top risk');
  return res.json();
}

export async function getRiskSummary() {
  const res = await fetch(`${API_BASE}/risk/summary`);
  if (!res.ok) throw apiError(res, 'Failed to get risk summary');
  return res.json();
}

export async function getSignals(projectId) {
  const res = await fetch(`${API_BASE}/signals/${encodeURIComponent(projectId)}`);
  if (!res.ok) throw apiError(res, 'Failed to get signals');
  return res.json();
}

export async function getEvidence(projectId) {
  const res = await fetch(`${API_BASE}/evidence/${encodeURIComponent(projectId)}`);
  if (!res.ok) throw apiError(res, 'Failed to get evidence');
  return res.json();
}

export async function getContext(projectId) {
  const res = await fetch(`${API_BASE}/context/${encodeURIComponent(projectId)}`);
  if (!res.ok) throw apiError(res, 'Failed to get context');
  return res.json();
}

export async function getInvestigations() {
  const res = await fetch(`${API_BASE}/investigations`);
  if (!res.ok) throw apiError(res, 'Failed to get investigations');
  return res.json();
}

export async function recalculateRisk(projectId) {
  const res = await fetch(`${API_BASE}/risk/recalculate/${encodeURIComponent(projectId)}`, { method: 'POST' });
  if (!res.ok) throw apiError(res, 'Failed to recalculate risk');
  return res.json();
}
