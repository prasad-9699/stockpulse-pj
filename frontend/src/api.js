/**
 * api.js — Centralized API client for StockPulse backend.
 * All fetch calls go through this module for consistent error handling.
 */

const API_BASE = 'http://localhost:8000';

/**
 * Generic fetch wrapper with error handling.
 * Throws an Error with the response detail on non-2xx responses.
 */
async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API error');
  }
  return res.json();
}

/** Fetch all products with optional status and category filters. */
export function fetchProducts(status, category) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (category) params.set('category', category);
  const qs = params.toString();
  return apiFetch(`/products${qs ? '?' + qs : ''}`);
}

/** Fetch a single product by ID with nested suggestions. */
export function fetchProduct(id) {
  return apiFetch(`/products/${id}`);
}

/** Simulate a sale — decrement stock by qty and bump demand velocity. */
export function simulateOrder(productId, qty = 1) {
  return apiFetch(`/products/${productId}/orders`, {
    method: 'POST',
    body: JSON.stringify({ qty }),
  });
}

/** Update a product's stock level directly. */
export function updateStock(productId, stockLevel) {
  return apiFetch(`/products/${productId}/stock`, {
    method: 'PATCH',
    body: JSON.stringify({ stock_level: stockLevel }),
  });
}

/** Fetch all pricing suggestions, optionally filtered by status. */
export function fetchPricingSuggestions(status) {
  const qs = status ? `?status=${status}` : '';
  return apiFetch(`/pricing-suggestions${qs}`);
}

/** Fetch all reorder suggestions, optionally filtered by status. */
export function fetchReorderSuggestions(status) {
  const qs = status ? `?status=${status}` : '';
  return apiFetch(`/reorder-suggestions${qs}`);
}

/** Accept or reject a pricing suggestion. */
export function updatePricingSuggestion(id, status) {
  return apiFetch(`/pricing-suggestions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

/** Accept or reject a reorder suggestion. */
export function updateReorderSuggestion(id, status) {
  return apiFetch(`/reorder-suggestions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
}

/** Request an on-demand pricing suggestion. */
export function requestPricingSuggestion(productId) {
  return apiFetch(`/products/${productId}/suggest-pricing`, { method: 'POST' });
}

/** Request an on-demand reorder suggestion. */
export function requestReorderSuggestion(productId) {
  return apiFetch(`/products/${productId}/suggest-reorder`, { method: 'POST' });
}

// ──────────────────── Advanced Feature APIs ────────────────────

/** Simulate a demand spike for a product. */
export function simulateDemandSpike(productId, multiplier = 3) {
  return apiFetch(`/products/${productId}/simulate-demand-spike`, {
    method: 'POST',
    body: JSON.stringify({ multiplier }),
  });
}

/** Get the currently active strategy. */
export function fetchStrategy() {
  return apiFetch('/settings/strategy');
}

/** Switch strategy between AI and RULE_BASED. */
export function updateStrategy(strategy) {
  return apiFetch('/settings/strategy', {
    method: 'PATCH',
    body: JSON.stringify({ strategy }),
  });
}

/** Fetch analytics overview with real database data. */
export function fetchAnalytics() {
  return apiFetch('/analytics');
}

/** Run a what-if simulation (does NOT modify DB). */
export function runWhatIf(productId, stockLevel, demandVelocity) {
  return apiFetch(`/products/${productId}/what-if`, {
    method: 'POST',
    body: JSON.stringify({ stock_level: stockLevel, demand_velocity: demandVelocity }),
  });
}

/** Fetch recommendation history with optional filters. */
export function fetchRecommendationHistory(status, type) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (type) params.set('suggestion_type', type);
  const qs = params.toString();
  return apiFetch(`/recommendations/history${qs ? '?' + qs : ''}`);
}

/** SSE base URL for the Agent Activity Feed. */
export const SSE_URL = `${API_BASE}/events/stream`;

