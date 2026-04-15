/**
 * JERA FX Investment API client.
 * Fetches from both /v1/client/* and /v1/investment/* endpoints.
 */

const API_BASE = window.JERA_API_BASE || 'http://127.0.0.1:8000';

async function apiFetch(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`);
    if (!res.ok) return { ok: false, data: null, error: `HTTP ${res.status}` };
    const data = await res.json();
    return { ok: true, data, error: null };
  } catch (e) {
    return { ok: false, data: null, error: e.message };
  }
}

export const api = {
  // Client endpoints (shared data)
  overview:            () => apiFetch('/v1/client/overview'),
  reerBands:           () => apiFetch('/v1/client/reer-bands'),
  ptaxHistory:         () => apiFetch('/v1/client/ptax-history'),
  sourceFreshness:     () => apiFetch('/v1/client/source-freshness'),
  tacticalSignal:      () => apiFetch('/v1/client/tactical-signal'),
  tacticalDrivers:     () => apiFetch('/v1/client/tactical-drivers'),
  scenarios:           () => apiFetch('/v1/client/scenarios'),
  driverFreshness:     () => apiFetch('/v1/client/tactical-driver-freshness'),

  // Investment-only endpoints
  rollingRegression:   () => apiFetch('/v1/investment/rolling-regression'),
  driverVariations:    () => apiFetch('/v1/investment/driver-variations'),
};
