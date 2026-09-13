import { apiGet, buildQuery } from "./client";

// Mirrors GET /search's query params exactly (backend/routers/search.py).
export function searchEvents(params) {
  return apiGet(`/search${buildQuery(params)}`);
}

export function statsTop(field, params) {
  return apiGet(`/stats/top${buildQuery({ field, ...params })}`);
}

export function statsTimeline(params) {
  return apiGet(`/stats/timeline${buildQuery(params)}`);
}
