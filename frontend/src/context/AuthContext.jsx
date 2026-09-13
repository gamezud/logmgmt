import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCurrentUser, login as loginRequest } from "../api/auth";
import { setUnauthorizedHandler } from "../api/client";

// JWT storage: sessionStorage, not localStorage or in-memory-only — survives
// a page reload within the same tab (so the demo doesn't re-prompt login on
// every refresh) without persisting past the tab closing. Both
// sessionStorage and localStorage are equally JS-readable (an XSS bug
// elsewhere in the app could read either); that's mitigated by not having
// an XSS hole, not by the storage location. httpOnly cookies were ruled out
// because the assignment's own wording ("store the JWT, attach it as an
// Authorization header") already implies the frontend manually attaches
// it, which a cookie the browser sends automatically isn't. See
// docs/DECISIONS.md.
const TOKEN_STORAGE_KEY = "access_token";

const AuthContext = createContext(null);

function readStoredToken() {
  try {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [token, setToken] = useState(readStoredToken);
  const [claims, setClaims] = useState(null); // { sub, role, tenant } from GET /auth/me
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    try {
      sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    } catch {
      // Storage can throw in a private window with site data blocked —
      // clearing in-memory state below is what actually matters.
    }
    setToken(null);
    setClaims(null);
    navigate("/login", { replace: true });
  }, [navigate]);

  useEffect(() => {
    // The one piece of plumbing that lets a 401 caught in api/client.js —
    // which has no React component of its own to call useNavigate from —
    // reach back into this context's logout. Registered once, here.
    setUnauthorizedHandler(logout);
  }, [logout]);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    // Populate role/tenant from the verified claims the server hands back,
    // rather than decoding the JWT client-side. If the stored token has
    // expired, this 401s and setUnauthorizedHandler's callback (logout)
    // already handles it — no separate handling needed here.
    fetchCurrentUser()
      .then(setClaims)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const login = useCallback(async (username, password) => {
    const { access_token: accessToken } = await loginRequest(username, password);
    try {
      sessionStorage.setItem(TOKEN_STORAGE_KEY, accessToken);
    } catch {
      // Worst case if storage is blocked: the token still works for this
      // page's lifetime via React state, a reload just requires logging in
      // again.
    }
    setToken(accessToken);
    const currentUser = await fetchCurrentUser();
    setClaims(currentUser);
    return currentUser;
  }, []);

  const value = {
    token,
    claims,
    loading,
    isAuthenticated: Boolean(token),
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
