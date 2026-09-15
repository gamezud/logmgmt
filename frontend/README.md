# frontend

React + Vite + Recharts dashboard: Login, Dashboard, Search, and Alerts
pages against the FastAPI backend. See `docs/DECISIONS.md` for the design
rationale behind every non-obvious choice below (JWT storage, why
`react-router-dom` was added, `/auth/me` over client-side decoding, why
there's no client-side expiry timer, why Top-N is a table not a chart, and
the accepted `npm audit` findings).

## Running

Needs the backend running first (`make up` from the repo root, plus at
least one user account via `backend/create_user.py` — see
`samples/README.md`).

```bash
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env.local` (Vite's own convention) and change
`VITE_API_BASE_URL` if the backend isn't at `http://localhost:8000`.

The dev server runs on Vite's default port, `5173`, which is also
`backend/config.py`'s default `FRONTEND_ORIGIN` for CORS — no extra config
needed for the two to talk to each other locally.

## Pages

- **Login** — `POST /auth/login`, then `GET /auth/me` to populate the
  displayed role/tenant (not a client-side JWT decode — see
  `docs/DECISIONS.md`).
- **Dashboard** — a time-range filter (presets + custom range) driving a
  Recharts timeline (`GET /stats/timeline`) and three Top-N tables
  (`GET /stats/top` for `ip`/`user`/`event_type`). No tenant selector
  anywhere in this app: tenant comes from the caller's JWT claim, never a
  client-side filter.
- **Search** — mirrors `GET /search`'s filters exactly; each result row is
  a native `<details>` element that expands to the original `raw` payload.
- **Alerts** — the `failed_login_burst` rule's config (editable for admin,
  read-only for viewer — enforcement is server-side either way) plus a
  paginated list of fired alerts (`GET /alerts`).

## Auth

The JWT lives in `sessionStorage` (`context/AuthContext.jsx`) and is
attached as `Authorization: Bearer <token>` by every request
(`api/client.js`). Any 401 response — including an expired token, which
the backend already turns into a plain 401 — clears the stored token and
redirects to `/login`; there's no separate client-side expiry timer.

## Known gaps (accepted, not implemented)

- No JS test runner — the assignment's "≥2-3 tests" requirement is already
  met by the existing pytest suite (`tests/`).
- `npm audit` reports 4 findings (an `esbuild` dev-server-only issue via
  `vite`, and an SSR/open-redirect issue via `react-router-dom` that
  doesn't apply to this CSR-only app with no user-controlled redirect
  targets) — deliberately not fixed via `--force` this session, since doing
  so would pull in two unrelated breaking major versions (`vite` 5→8,
  `react-router-dom` 6→7) with no time budgeted to verify the migration.
  See `docs/DECISIONS.md`.
