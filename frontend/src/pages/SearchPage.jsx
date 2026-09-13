import { useEffect, useState } from "react";

import { searchEvents } from "../api/events";

const DEFAULT_LIMIT = 50;

const EMPTY_FILTERS = { start_time: "", end_time: "", source: "", event_type: "", user: "", src_ip: "" };

function toIsoOrEmpty(localDateTimeValue) {
  return localDateTimeValue ? new Date(localDateTimeValue).toISOString() : "";
}

export default function SearchPage() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState({ items: [], has_more: false });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function runSearch(nextOffset) {
    setLoading(true);
    setError(null);
    searchEvents({ ...filters, limit: DEFAULT_LIMIT, offset: nextOffset })
      .then((data) => {
        setResult(data);
        setOffset(nextOffset);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  // Runs the unfiltered search once on mount; further searches are
  // triggered explicitly by submitting the filter form.
  useEffect(() => {
    runSearch(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleFilterSubmit(event) {
    event.preventDefault();
    runSearch(0);
  }

  function updateFilter(field, value) {
    setFilters((previous) => ({ ...previous, [field]: value }));
  }

  return (
    <div className="search-page">
      <h1>Search</h1>
      <form className="search-filters" onSubmit={handleFilterSubmit}>
        <label>
          Start
          <input type="datetime-local" onChange={(event) => updateFilter("start_time", toIsoOrEmpty(event.target.value))} />
        </label>
        <label>
          End
          <input type="datetime-local" onChange={(event) => updateFilter("end_time", toIsoOrEmpty(event.target.value))} />
        </label>
        <label>
          Source
          <input
            value={filters.source}
            placeholder="api, ad, aws…"
            onChange={(event) => updateFilter("source", event.target.value)}
          />
        </label>
        <label>
          Event type
          <input value={filters.event_type} onChange={(event) => updateFilter("event_type", event.target.value)} />
        </label>
        <label>
          User
          <input value={filters.user} onChange={(event) => updateFilter("user", event.target.value)} />
        </label>
        <label>
          Source IP
          <input value={filters.src_ip} onChange={(event) => updateFilter("src_ip", event.target.value)} />
        </label>
        <button type="submit">Search</button>
      </form>

      {error && <p className="form-error">{error}</p>}
      {loading ? (
        <p>Loading…</p>
      ) : (
        <>
          <div className="search-results">
            <div className="search-results-header">
              <span>Time</span>
              <span>Source</span>
              <span>Event type</span>
              <span>Severity</span>
              <span>Action</span>
              <span>Src IP</span>
              <span>User</span>
              <span>Host</span>
            </div>
            {result.items.map((item) => (
              // Each row is a native <details> element — clicking it
              // expands the original raw payload (docs/DECISIONS.md #1:
              // the original message is always preserved in `raw`),
              // without needing any extra library for the disclosure widget.
              <details key={item.id} className="search-result-row">
                <summary>
                  <span>{new Date(item["@timestamp"]).toLocaleString()}</span>
                  <span>{item.source}</span>
                  <span>{item.event_type}</span>
                  <span>{item.severity ?? "—"}</span>
                  <span>{item.action ?? "—"}</span>
                  <span>{item.src_ip ?? "—"}</span>
                  <span>{item.user ?? "—"}</span>
                  <span>{item.host ?? "—"}</span>
                </summary>
                <pre className="raw-json">{JSON.stringify(item.raw, null, 2)}</pre>
              </details>
            ))}
          </div>
          {result.items.length === 0 && <p className="empty-state">No events match these filters.</p>}
          <div className="pagination">
            <button type="button" disabled={offset === 0} onClick={() => runSearch(Math.max(0, offset - DEFAULT_LIMIT))}>
              Previous
            </button>
            <button type="button" disabled={!result.has_more} onClick={() => runSearch(offset + DEFAULT_LIMIT)}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
