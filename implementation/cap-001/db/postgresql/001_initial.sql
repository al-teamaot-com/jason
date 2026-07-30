BEGIN;

CREATE TABLE cases (
    case_id text PRIMARY KEY,
    correlation_id text NOT NULL UNIQUE,
    client_id text NOT NULL,
    request_id text,
    state text NOT NULL,
    case_document jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_cases_client_created ON cases(client_id, created_at DESC);

CREATE TABLE reasoning_results (
    result_id uuid PRIMARY KEY,
    case_id text NOT NULL REFERENCES cases(case_id),
    result_document jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outcomes (
    outcome_id uuid PRIMARY KEY,
    case_id text NOT NULL REFERENCES cases(case_id),
    outcome_document jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workflow_transitions (
    transition_id uuid PRIMARY KEY,
    case_id text,
    correlation_id text NOT NULL,
    from_state text NOT NULL,
    to_state text NOT NULL,
    reason text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_transitions_correlation ON workflow_transitions(correlation_id, occurred_at);

CREATE TABLE audit_events (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    correlation_id text,
    case_id text,
    client_id text,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_correlation ON audit_events(correlation_id, occurred_at);
CREATE INDEX ix_audit_client ON audit_events(client_id, occurred_at);

-- Tenant isolation is enforced in application code for the pilot. Before a
-- production deployment, enable PostgreSQL row-level security and bind
-- current_setting('jason.client_id') to each transaction.

COMMIT;
