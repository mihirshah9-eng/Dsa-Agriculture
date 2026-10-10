/**
 * KJS-AGR-01 | Member 1: Priority & Scheduling Engine
 * m1Api.js -- the only place that knows about URLs.
 *
 * Base URL resolution:
 *   - dev with Vite   -> '' and vite.config.js proxies /api to Flask:5000
 *   - served by Flask -> '' and the same origin answers
 *   - custom          -> set window.M1_API_BASE before the bundle loads
 */
const BASE = (typeof window !== 'undefined' && window.M1_API_BASE) || '';
const ROOT = `${BASE}/api/priority`;

async function request(path, options = {}) {
  const res = await fetch(`${ROOT}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && body.error) detail = body.error;
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.json();
}

/** Full simulator snapshot: counts, environment, schedule slots, pumps, alerts. */
export const getState = (scheduleRows = 288, alerts = 60) =>
  request(`/state?schedule_rows=${scheduleRows}&alerts=${alerts}`);

/** Live priority board rows, ordered by the chosen sorting algorithm. */
export const getPlots = ({ limit = 60, algorithm = 'counting', village, crop, status } = {}) => {
  const q = new URLSearchParams({ limit, algorithm });
  if (village) q.set('village', village);
  if (crop) q.set('crop', crop);
  if (status) q.set('status', status);
  return request(`/plots?${q.toString()}`);
};

export const getSchedule = (limit = 288) => request(`/schedule?limit=${limit}`);
export const getAlerts = (limit = 60) => request(`/alerts?limit=${limit}`);
export const getStructures = () => request('/structures');
export const getPumps = () => request('/pumps');
export const getPlotTrend = (plotId) => request(`/trend/${plotId}`);
export const getBenchmarks = () => request('/benchmarks');
export const getHealth = () => request('/health');

/** Fire a named simulation event: drought | rain | power_cut | heatwave | burst | reset | run | speed */
export const postControl = (event, value) =>
  request('/control', { method: 'POST', body: JSON.stringify({ event, value }) });

/** Advance the simulated clock by `count` ticks (demo step button). */
export const postStep = (count = 1) =>
  request('/step', { method: 'POST', body: JSON.stringify({ count }) });

export const postPlotCount = (plotCount) =>
  request('/plot-count', { method: 'POST', body: JSON.stringify({ plot_count: plotCount }) });

export const postSortCompare = (algorithm = 'all') =>
  request('/sort-compare', { method: 'POST', body: JSON.stringify({ algorithm }) });

export { ROOT as M1_API_ROOT };
