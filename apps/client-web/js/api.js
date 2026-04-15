/**
 * JERA FX Client API — fetch wrapper for /v1/client/* endpoints.
 *
 * Every function returns { ok, data, error } so the caller can render
 * graceful degradation without try/catch boilerplate.
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
  overview:            () => apiFetch('/v1/client/overview'),
  reerBands:           () => apiFetch('/v1/client/reer-bands'),
  ptaxHistory:         () => apiFetch('/v1/client/ptax-history'),
  sourceFreshness:     () => apiFetch('/v1/client/source-freshness'),
  tacticalSignal:      () => apiFetch('/v1/client/tactical-signal'),
  tacticalDrivers:     () => apiFetch('/v1/client/tactical-drivers'),
  tacticalReadiness:   () => apiFetch('/v1/client/tactical-signal-readiness'),
  tacticalInputs:      () => apiFetch('/v1/client/tactical-inputs'),
  driverFreshness:     () => apiFetch('/v1/client/tactical-driver-freshness'),
  scenarios:           () => apiFetch('/v1/client/scenarios'),
};
