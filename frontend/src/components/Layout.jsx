import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function Layout() {
  const { claims, logout } = useAuth();

  return (
    <div className="app-shell">
      <header className="app-header">
        <nav className="app-nav">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/search">Search</NavLink>
          <NavLink to="/alerts">Alerts</NavLink>
        </nav>
        <div className="app-user">
          {claims && (
            <span className="app-user-info">
              {claims.sub} · {claims.role} · {claims.tenant}
            </span>
          )}
          <button type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
