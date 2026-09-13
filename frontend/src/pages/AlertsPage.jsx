import { useEffect, useState } from "react";

import { createAlertRule, listAlertRules, listAlerts, updateAlertRule } from "../api/alerts";
import { useAuth } from "../context/AuthContext";

const DEFAULT_LIMIT = 50;
const DEFAULT_RULE_FORM = { threshold: 5, window_seconds: 300, cooldown_seconds: 900, enabled: true };

export default function AlertsPage() {
  const { claims } = useAuth();
  const isAdmin = claims?.role === "admin";

  const [rule, setRule] = useState(null);
  const [ruleForm, setRuleForm] = useState(DEFAULT_RULE_FORM);
  const [ruleError, setRuleError] = useState(null);
  const [ruleSaving, setRuleSaving] = useState(false);

  const [alerts, setAlerts] = useState({ items: [], has_more: false });
  const [offset, setOffset] = useState(0);
  const [loadingAlerts, setLoadingAlerts] = useState(true);
  const [alertsError, setAlertsError] = useState(null);

  useEffect(() => {
    listAlertRules()
      .then((rules) => {
        const existing = rules[0] ?? null;
        setRule(existing);
        if (existing) {
          setRuleForm({
            threshold: existing.threshold,
            window_seconds: existing.window_seconds,
            cooldown_seconds: existing.cooldown_seconds,
            enabled: existing.enabled,
          });
        }
      })
      .catch((err) => setRuleError(err.message));
  }, []);

  function loadAlerts(nextOffset) {
    setLoadingAlerts(true);
    setAlertsError(null);
    listAlerts({ limit: DEFAULT_LIMIT, offset: nextOffset })
      .then((data) => {
        setAlerts(data);
        setOffset(nextOffset);
      })
      .catch((err) => setAlertsError(err.message))
      .finally(() => setLoadingAlerts(false));
  }

  useEffect(() => {
    loadAlerts(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleRuleSubmit(event) {
    event.preventDefault();
    setRuleSaving(true);
    setRuleError(null);
    try {
      const saved = rule ? await updateAlertRule(rule.id, ruleForm) : await createAlertRule(ruleForm);
      setRule(saved);
    } catch (err) {
      setRuleError(err.message);
    } finally {
      setRuleSaving(false);
    }
  }

  function updateField(field, value) {
    setRuleForm((previous) => ({ ...previous, [field]: value }));
  }

  return (
    <div className="alerts-page">
      <h1>Alerts</h1>

      <section className="alert-rule-panel">
        <h2>Failed Login Burst Rule</h2>
        {/* Admin edits these fields; viewer sees the same form read-only
            (all inputs disabled). This is a UX nicety only — the real
            enforcement is server-side (require_role("admin") on
            POST/PATCH /alert-rules); a viewer calling those endpoints
            directly still gets a 403 regardless of what this form shows. */}
        <form onSubmit={handleRuleSubmit}>
          <label>
            Threshold (failed logins)
            <input
              type="number"
              min="1"
              value={ruleForm.threshold}
              disabled={!isAdmin}
              onChange={(event) => updateField("threshold", Number(event.target.value))}
            />
          </label>
          <label>
            Window (seconds)
            <input
              type="number"
              min="1"
              value={ruleForm.window_seconds}
              disabled={!isAdmin}
              onChange={(event) => updateField("window_seconds", Number(event.target.value))}
            />
          </label>
          <label>
            Cooldown (seconds)
            <input
              type="number"
              min="1"
              value={ruleForm.cooldown_seconds}
              disabled={!isAdmin}
              onChange={(event) => updateField("cooldown_seconds", Number(event.target.value))}
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={ruleForm.enabled}
              disabled={!isAdmin}
              onChange={(event) => updateField("enabled", event.target.checked)}
            />
            Enabled
          </label>
          {isAdmin && (
            <button type="submit" disabled={ruleSaving}>
              {ruleSaving ? "Saving…" : rule ? "Save changes" : "Create rule"}
            </button>
          )}
        </form>
        {ruleError && <p className="form-error">{ruleError}</p>}
        {!rule && !isAdmin && <p className="empty-state">No alert rule configured for this tenant yet.</p>}
      </section>

      <section className="alerts-list">
        <h2>Recent Alerts</h2>
        {alertsError && <p className="form-error">{alertsError}</p>}
        {loadingAlerts ? (
          <p>Loading…</p>
        ) : alerts.items.length === 0 ? (
          <p className="empty-state">No alerts fired yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Triggered</th>
                <th>Source IP</th>
                <th>Count</th>
                <th>Threshold</th>
                <th>Event window</th>
                <th>Webhook</th>
              </tr>
            </thead>
            <tbody>
              {alerts.items.map((alert) => (
                <tr key={alert.id}>
                  <td>{new Date(alert.triggered_at).toLocaleString()}</td>
                  <td>{alert.src_ip}</td>
                  <td>{alert.event_count}</td>
                  <td>{alert.threshold}</td>
                  <td>
                    {/* window_start/window_end are the real event_time span
                        the source claims, not the ingested_at window that
                        actually decided whether this fired — see
                        docs/DECISIONS.md. */}
                    {new Date(alert.window_start).toLocaleTimeString()} – {new Date(alert.window_end).toLocaleTimeString()}
                  </td>
                  <td>{alert.webhook_sent_at ? "sent" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="pagination">
          <button type="button" disabled={offset === 0} onClick={() => loadAlerts(Math.max(0, offset - DEFAULT_LIMIT))}>
            Previous
          </button>
          <button type="button" disabled={!alerts.has_more} onClick={() => loadAlerts(offset + DEFAULT_LIMIT)}>
            Next
          </button>
        </div>
      </section>
    </div>
  );
}
