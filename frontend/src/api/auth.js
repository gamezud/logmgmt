import { apiGet, apiPost } from "./client";

export function login(username, password) {
  return apiPost("/auth/login", { username, password });
}

// Called right after login to populate role/tenant, instead of decoding the
// JWT client-side — /auth/me exists precisely to hand back verified claims
// (backend/routers/auth.py), so this avoids adding a JWT-decoding routine
// to the frontend and guarantees what's displayed can never drift from
// what the server will actually enforce. See docs/DECISIONS.md.
export function fetchCurrentUser() {
  return apiGet("/auth/me");
}
