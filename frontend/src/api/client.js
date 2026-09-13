// Thin fetch wrapper: attaches `Authorization: Bearer <token>` to every
// request (reading the token from sessionStorage — see
// context/AuthContext.jsx and docs/DECISIONS.md for why sessionStorage over
// localStorage/in-memory/httpOnly cookie), and on any 401 response calls a
// registered "log out" callback before rejecting.
//
// Why a plain module-level callback instead of importing a router hook
// here: this file has no React component of its own — it's called from
// page components, but a 401 can happen at any time, including from a
// fetch this module issues on its own. AuthContext registers the actual
// "clear the token and redirect to /login" behavior once, at app startup,
// via setUnauthorizedHandler — that's the one piece of plumbing that lets a
// 401 caught here reach back into React's router state.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

let onUnauthorized = () => {};

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

function getToken() {
  try {
    return sessionStorage.getItem("access_token");
  } catch {
    // Storage can throw in a private window with site data blocked — treat
    // it the same as "not logged in" rather than crashing the app.
    return null;
  }
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.body !== undefined && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401) {
    // Covers both "the token expired" and "got a 401 for any other
    // reason" with the same handler — an expired token sent to any
    // endpoint already comes back as a plain 401
    // (backend/deps.py:get_current_claims), so there's no separate
    // client-side expiry timer to keep in sync with the backend's
    // JWT_EXPIRE_MINUTES. See docs/DECISIONS.md.
    onUnauthorized();
    throw new Error("unauthorized");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return null;
  }
  return response.json();
}

// Builds a query string from a plain object, dropping null/undefined/empty
// values so optional filters don't show up as e.g. "?source=" in the URL.
export function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      search.set(key, value);
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function apiGet(path) {
  return apiFetch(path);
}

export function apiPost(path, body) {
  return apiFetch(path, { method: "POST", body: JSON.stringify(body ?? {}) });
}

export function apiPatch(path, body) {
  return apiFetch(path, { method: "PATCH", body: JSON.stringify(body ?? {}) });
}
