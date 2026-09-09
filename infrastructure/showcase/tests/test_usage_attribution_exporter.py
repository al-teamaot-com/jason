from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def load_exporter():
    path = Path(__file__).resolve().parents[1] / "usage_attribution_exporter.py"
    spec = importlib.util.spec_from_file_location("jason_usage_attribution_exporter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def create_model_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE model_usage_entries (
            entry_id TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE (organization_id, attempt_id)
        );
        CREATE TABLE model_usage_adjustments (
            adjustment_id TEXT PRIMARY KEY,
            original_entry_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """
    )
    attributed = {
        "entry_id": "model-1",
        "context": {
            "workflow_id": "conv-1",
            "request_id": "msg-1",
            "attempt_id": "attempt-1",
            "organization_id": "aot",
            "client_id": None,
            "capability": "conversation.reason",
            "agent_name": None,
            "routing_profile": "teams",
            "metadata": {
                "correlation_id": "corr-human-1",
                "actor_type": "human",
                "actor_id": "user-al",
                "source_channel": "teams",
                "purpose": "Resolve managed endpoint state",
                "email_address": "al@teamaot.com",
                "api_key": "never-export",
                "prompt": "never-export-prompt",
            },
        },
        "provider": "openai",
        "model": "gpt-5-nano",
        "outcome": "completed",
        "usage_source": "provider_reported",
        "tokens": {
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 50,
            "reasoning_tokens": 0,
            "total_tokens": 150,
        },
        "cost": {
            "provider_reported_cost": None,
            "calculated_cost": "0.00002500",
            "currency": "USD",
        },
        "completed_at": "2026-09-09T15:00:00+00:00",
    }
    unknown = {
        "entry_id": "model-2",
        "context": {
            "workflow_id": "unattributed-runtime",
            "request_id": "unattributed-1",
            "attempt_id": "attempt-2",
            "organization_id": "aot",
            "client_id": None,
            "capability": "unknown",
            "routing_profile": "unattributed-runtime",
            "metadata": {
                "actor_type": "unknown",
                "actor_id": "unknown",
                "source_channel": "unknown",
                "purpose": "unattributed model invocation",
            },
        },
        "provider": "openai",
        "model": "gpt-5-nano",
        "outcome": "completed",
        "usage_source": "provider_reported",
        "tokens": {"total_tokens": 25},
        "cost": {"calculated_cost": "0.000005", "currency": "USD"},
        "completed_at": "2026-09-09T15:05:00+00:00",
    }
    for payload in (attributed, unknown):
        connection.execute(
            "INSERT INTO model_usage_entries VALUES (?, 'aot', ?, ?)",
            (payload["entry_id"], payload["context"]["attempt_id"], json.dumps(payload)),
        )
    connection.commit()
    connection.close()


def create_events_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE orchestration_events (
            event_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            event_type TEXT NOT NULL,
            execution_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            capability_name TEXT NOT NULL,
            stage TEXT NOT NULL,
            payload TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        """
    )

    def insert(event_id, event_type, execution_id, correlation_id, principal, capability, stage, payload, occurred_at):
        connection.execute(
            "INSERT INTO orchestration_events VALUES (?, '1.0', ?, ?, ?, 'aot', ?, ?, ?, ?, ?)",
            (
                event_id,
                event_type,
                execution_id,
                correlation_id,
                principal,
                capability,
                stage,
                json.dumps(payload),
                occurred_at,
            ),
        )

    insert(
        "request-mcp",
        "orchestration.request.received",
        "exec_mcp_1",
        "corr_mcp_1",
        "user-al",
        "endpoint.device.search",
        "received",
        {
            "requester_kind": "human",
            "token": "never-export-token",
        },
        "2026-09-09T15:10:00+00:00",
    )
    insert(
        "connector-mcp",
        "connector.requested",
        "connector:corr_mcp_1",
        "corr_mcp_1",
        "user-al",
        "endpoint.device.search",
        "invoking",
        {
            "details": {
                "provider": "datto_rmm",
                "operation": "/v2/account/devices",
                "authorization": "never-export-authorization",
            }
        },
        "2026-09-09T15:10:01+00:00",
    )
    insert(
        "request-service",
        "orchestration.request.received",
        "exec-svc",
        "corr-svc",
        "svc-newman",
        "email.send",
        "received",
        {"requester_kind": "service"},
        "2026-09-09T15:20:00+00:00",
    )
    insert(
        "email-attempt",
        "email.send.attempted",
        "exec-svc",
        "corr-svc",
        "svc-newman",
        "email.send",
        "invoking",
        {"recipient": "not-exported@example.com"},
        "2026-09-09T15:20:01+00:00",
    )
    connection.commit()
    connection.close()


def create_bindings_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE microsoft_identity_bindings (
            microsoft_tenant_id TEXT NOT NULL,
            microsoft_object_id TEXT NOT NULL,
            jason_identity_id TEXT NOT NULL,
            client_id TEXT,
            email_address TEXT,
            status TEXT NOT NULL,
            PRIMARY KEY (microsoft_tenant_id, microsoft_object_id)
        )
        """
    )
    connection.execute(
        "INSERT INTO microsoft_identity_bindings VALUES ('tenant', 'oid', 'user-al', NULL, 'al@teamaot.com', 'active')"
    )
    connection.commit()
    connection.close()


def test_exporter_traces_actor_provider_billing_and_attribution_gaps(tmp_path):
    module = load_exporter()
    module.MODEL_USAGE_DB = tmp_path / "model.sqlite3"
    module.ORCHESTRATION_EVENTS_DB = tmp_path / "events.sqlite3"
    module.IDENTITY_BINDINGS_DB = tmp_path / "bindings.sqlite3"
    module.MAX_RECENT_EVENT_SERIES = 50
    create_model_db(module.MODEL_USAGE_DB)
    create_events_db(module.ORCHESTRATION_EVENTS_DB)
    create_bindings_db(module.IDENTITY_BINDINGS_DB)

    metrics = module.render_metrics(datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc))

    assert 'jason_usage_observed_events_24h{kind="model"} 2' in metrics
    assert 'jason_usage_observed_events_24h{kind="provider_api"} 2' in metrics
    assert "jason_usage_unattributed_events_24h 1" in metrics
    assert "jason_usage_attribution_coverage_ratio_24h 0.750000" in metrics
    assert 'actor_id="user-al",email="al@teamaot.com"' in metrics
    assert 'actor_id="svc-newman"' in metrics
    assert 'source_channel="chatgpt_mcp"' in metrics
    assert 'provider="datto_rmm",product="Datto RMM",billing_class="subscription"' in metrics
    assert 'provider="aws_ses",product="AWS SES",billing_class="metered"' in metrics
    assert 'provider="openai",product="OpenAI API"' in metrics
    assert 'correlation_id="corr_mcp_1"' in metrics
    assert 'purpose="endpoint.device.search: /v2/account/devices"' in metrics
    assert "never-export" not in metrics
    assert "never-export-token" not in metrics
    assert "never-export-authorization" not in metrics
    assert "not-exported@example.com" not in metrics


def test_missing_sources_fail_closed_without_creating_files(tmp_path):
    module = load_exporter()
    module.MODEL_USAGE_DB = tmp_path / "missing-model.sqlite3"
    module.ORCHESTRATION_EVENTS_DB = tmp_path / "missing-events.sqlite3"
    module.IDENTITY_BINDINGS_DB = tmp_path / "missing-bindings.sqlite3"

    metrics = module.render_metrics(datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc))

    assert 'source="model_usage"} 0' in metrics
    assert 'source="orchestration_events"} 0' in metrics
    assert 'source="identity_bindings"} 0' in metrics
    assert "jason_usage_unattributed_events_24h 0" in metrics
    assert not module.MODEL_USAGE_DB.exists()
    assert not module.ORCHESTRATION_EVENTS_DB.exists()
    assert not module.IDENTITY_BINDINGS_DB.exists()
