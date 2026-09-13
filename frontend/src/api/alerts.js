import { apiGet, apiPatch, apiPost, buildQuery } from "./client";

export function listAlerts(params) {
  return apiGet(`/alerts${buildQuery(params)}`);
}

export function listAlertRules() {
  return apiGet("/alert-rules");
}

// Admin-only server-side (require_role("admin") — backend/routers/alert_rules.py).
// A viewer calling these gets a 403; the frontend hiding the edit form for
// viewer is a UX nicety on top of that, not the security boundary itself.
export function createAlertRule(body) {
  return apiPost("/alert-rules", body);
}

export function updateAlertRule(id, body) {
  return apiPatch(`/alert-rules/${id}`, body);
}
