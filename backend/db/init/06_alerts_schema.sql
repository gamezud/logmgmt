-- alert_rules + alerts: the required "≥1 alert rule + notification"
-- capability (assignment §2.2/§8). Same tenant-isolation shape as `events`
-- (ENABLE + FORCE ROW LEVEL SECURITY, a tenant_isolation policy comparing
-- against current_setting('app.tenant', true) — see 02_schema.sql and
-- docs/DECISIONS.md #6-#8 for why this is enforced at the DB layer, not
-- just WHERE tenant = ? in application code). See docs/DECISIONS.md for the
-- full write-up of every choice below.

-- One row per (tenant, rule_type) — only 'failed_login_burst' exists this
-- session, but the column exists now so a future rule type is an additive
-- CHECK-list change, not a schema migration to introduce the concept.
CREATE TABLE alert_rules (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tenant           text NOT NULL CHECK (tenant <> ''),
    rule_type        text NOT NULL CHECK (rule_type = 'failed_login_burst'),

    threshold        integer NOT NULL DEFAULT 5   CHECK (threshold > 0),
    window_seconds   integer NOT NULL DEFAULT 300 CHECK (window_seconds > 0),
    cooldown_seconds integer NOT NULL DEFAULT 900 CHECK (cooldown_seconds > 0),
    enabled          boolean NOT NULL DEFAULT true,

    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),

    -- One config per rule type per tenant — POST /alert-rules relies on
    -- this to reject a duplicate with 409 rather than silently creating an
    -- ambiguous second row the engine would have to choose between.
    UNIQUE (tenant, rule_type),

    -- Lets `alerts` below declare a composite FK on (tenant, rule_id),
    -- enforcing at the DB level that an alert can never reference a rule
    -- belonging to a different tenant than the alert itself — the same
    -- "enforce the invariant in the DB, not just by application code always
    -- happening to query things together" reasoning as the tenant CHECK
    -- constraints (docs/DECISIONS.md #20).
    UNIQUE (tenant, id)
);

ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_rules FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON alert_rules
    USING (tenant = current_setting('app.tenant', true))
    WITH CHECK (tenant = current_setting('app.tenant', true));

-- Not partitioned: alert_rules is tiny, admin-edited config, nothing like
-- events' continuous high-throughput insert pattern.

-- SELECT (GET /alert-rules, both roles) + INSERT (POST, admin) + UPDATE
-- (PATCH, admin — threshold/window/cooldown/enabled). No DELETE: disabling
-- via `enabled = false` covers "turn it off" without having to decide what
-- happens to `alerts` rows that reference a deleted rule.
GRANT SELECT, INSERT, UPDATE ON alert_rules TO app_user;

CREATE TABLE alerts (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant          text NOT NULL CHECK (tenant <> ''),
    rule_id         bigint NOT NULL,

    triggered_at    timestamptz NOT NULL DEFAULT now(),
    src_ip          inet NOT NULL,
    event_count     integer NOT NULL,

    -- Copied from the rule AT FIRE TIME, not just referenced via rule_id —
    -- so editing the rule's threshold/window later doesn't retroactively
    -- change what a historical alert is displayed as having fired on.
    threshold       integer NOT NULL,
    window_seconds  integer NOT NULL,

    -- MIN/MAX(event_time) of the matched rows: the real-world incident span
    -- the source claims. Deliberately NOT the ingested_at poll window that
    -- actually decided whether to fire — detection trusts ingested_at
    -- (immune to a source's clock skew), reporting trusts event_time (what
    -- an analyst investigating the alert actually wants to know). See
    -- docs/DECISIONS.md for the full comparison of event_time vs
    -- ingested_at vs this hybrid.
    window_start    timestamptz NOT NULL,
    window_end      timestamptz NOT NULL,

    -- Set by the engine after a successful webhook POST; stays NULL if no
    -- webhook is configured (ALERT_WEBHOOK_URL unset — the normal local-dev
    -- default, not an error) or if delivery failed. The alert row itself is
    -- never lost either way; only the delivery receipt is missing.
    webhook_sent_at timestamptz,

    FOREIGN KEY (tenant, rule_id) REFERENCES alert_rules (tenant, id)
);

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON alerts
    USING (tenant = current_setting('app.tenant', true))
    WITH CHECK (tenant = current_setting('app.tenant', true));

-- Not partitioned like `events`: alerts fire orders of magnitude less often
-- than raw log ingest (bounded by cooldown_seconds per src_ip), so there's
-- no continuous high-throughput write pattern to justify partition-drop
-- retention (docs/DECISIONS.md #9/#11's reasoning for events doesn't apply
-- here). No retention policy on alerts in this session — only `events`
-- retention (≥7 days) is a graded requirement.

-- SELECT (GET /alerts) + INSERT (the engine, one row per fired alert).
GRANT SELECT, INSERT ON alerts TO app_user;
-- Column-level, not a blanket UPDATE: the only mutation this table ever
-- needs is the engine recording "the webhook for this alert was
-- delivered" — same least-privilege reasoning as app_user's grants on
-- `events` (docs/DECISIONS.md #6).
GRANT UPDATE (webhook_sent_at) ON alerts TO app_user;

-- GET /alerts, ordered by recency for one tenant.
CREATE INDEX idx_alerts_tenant_time ON alerts (tenant, triggered_at DESC);

-- The cooldown lookup: MAX(triggered_at) WHERE tenant=%s AND rule_id=%s
-- AND src_ip=%s — an index-only backward scan for LIMIT 1.
CREATE INDEX idx_alerts_tenant_rule_srcip_time
    ON alerts (tenant, rule_id, src_ip, triggered_at DESC);
