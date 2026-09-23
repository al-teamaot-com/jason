from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_runtime_exporter():
    showcase = Path(__file__).resolve().parents[1]
    if str(showcase) not in sys.path:
        sys.path.insert(0, str(showcase))
    for name in ("usage_attribution_exporter_runtime", "usage_attribution_exporter"):
        sys.modules.pop(name, None)
    return importlib.import_module("usage_attribution_exporter_runtime")


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
    classifier = {
        "entry_id": "model-classifier",
        "context": {
            "workflow_id": "conv-2",
            "request_id": "msg-2",
            "attempt_id": "attempt-classifier",
            "organization_id": "aot",
            "client_id": None,
            "capability": "conversation.classify",
            "routing_profile": "teams",
            "metadata": {
                "correlation_id": "corr-teams-2",
                "actor_type": "unknown",
                "actor_id": "unknown",
                "source_channel": "teams",
                "purpose": "Classify Teams turn for governed information handling",
                "prompt": "never-export-classifier-prompt",
            },
        },
        "provider": "openai",
        "model": "gpt-5-nano",
        "outcome": "completed",
        "usage_source": "provider_reported",
        "tokens": {
            "input_tokens": 80,
            "cached_input_tokens": 0,
            "output_tokens": 20,
            "reasoning_tokens": 0,
            "total_tokens": 100,
        },
        "cost": {
            "provider_reported_cost": None,
            "calculated_cost": "0.00001200",
            "currency": "USD",
        },
        "completed_at": "2026-09-09T15:04:59+00:00",
    }
    connection.execute(
        "INSERT INTO model_usage_entries VALUES (?, 'aot', ?, ?)",
        (
            classifier["entry_id"],
            classifier["context"]["attempt_id"],
            json.dumps(classifier),
        ),
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
        "INSERT INTO microsoft_identity_bindings VALUES ('tenant-secret', 'object-secret', 'user-al', NULL, NULL, 'active')"
    )
    connection.commit()
    connection.close()


def create_events_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
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
        )
        """
    )

    def insert(event_id, event_type, execution_id, correlation_id, capability, stage, payload, occurred_at):
        connection.execute(
            "INSERT INTO orchestration_events VALUES (?, '1.0', ?, ?, ?, 'aot', 'user-al', ?, ?, ?, ?)",
            (
                event_id,
                event_type,
                execution_id,
                correlation_id,
                capability,
                stage,
                json.dumps(payload),
                occurred_at,
            ),
        )

    insert(
        "directory-request",
        "identity.directory.requested",
        "directory:msg-1",
        "teams-directory:conv-1:msg-1",
        "identity.profile.enrich",
        "invoking",
        {
            "requester_kind": "human",
            "request_id": "msg-1",
            "details": {
                "provider": "microsoft_graph",
                "product": "Microsoft Graph",
                "operation": "user.profile.read",
                "source_channel": "teams",
                "purpose": "Enrich authenticated Jason human identity with directory email",
                "access_token": "never-export-token",
                "microsoft_object_id": "never-export-object",
            },
        },
        "2026-09-09T15:00:00+00:00",
    )
    insert(
        "directory-complete",
        "identity.directory.completed",
        "directory:msg-1",
        "teams-directory:conv-1:msg-1",
        "identity.profile.enrich",
        "completed",
        {
            "requester_kind": "human",
            "request_id": "msg-1",
            "details": {
                "provider": "microsoft_graph",
                "operation": "user.profile.read",
                "outcome": "completed",
                "email_address": "al@teamaot.com",
            },
        },
        "2026-09-09T15:00:01+00:00",
    )
    insert(
        "request-datto",
        "orchestration.request.received",
        "exec-2",
        "corr-teams-2",
        "endpoint.device.search",
        "received",
        {"requester_kind": "human"},
        "2026-09-09T15:05:00+00:00",
    )
    insert(
        "connector-datto",
        "connector.requested",
        "connector:corr-teams-2",
        "corr-teams-2",
        "endpoint.device.search",
        "invoking",
        {
            "details": {
                "provider": "datto_rmm",
                "operation": "device.search",
                "authorization": "never-export-authorization",
            }
        },
        "2026-09-09T15:05:01+00:00",
    )
    connection.commit()
    connection.close()


def test_runtime_exporter_correlates_classifier_graph_and_provider_usage(tmp_path):
    module = load_runtime_exporter()
    base = module.base
    base.MODEL_USAGE_DB = tmp_path / "model.sqlite3"
    base.ORCHESTRATION_EVENTS_DB = tmp_path / "events.sqlite3"
    base.IDENTITY_BINDINGS_DB = tmp_path / "bindings.sqlite3"
    base.MAX_RECENT_EVENT_SERIES = 50

    create_model_db(base.MODEL_USAGE_DB)
    create_events_db(base.ORCHESTRATION_EVENTS_DB)
    create_bindings_db(base.IDENTITY_BINDINGS_DB)

    metrics = base.render_metrics(datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc))

    assert 'jason_usage_observed_events_24h{kind="model"} 1' in metrics
    assert 'jason_usage_observed_events_24h{kind="provider_api"} 2' in metrics
    assert "jason_usage_unattributed_events_24h 0" in metrics
    assert "jason_usage_attribution_coverage_ratio_24h 1.000000" in metrics
    assert "jason_usage_human_email_coverage_ratio_24h 1.000000" in metrics
    assert 'provider="microsoft_graph",product="Microsoft Graph",billing_class="subscription"' in metrics
    assert 'provider="datto_rmm",product="Datto RMM",billing_class="subscription"' in metrics
    assert 'provider="openai",product="OpenAI API"' in metrics
    assert 'actor_id="user-al",email="al@teamaot.com"' in metrics
    assert 'source_channel="teams"' in metrics
    assert 'service="user.profile.read"' in metrics
    assert 'correlation_id="teams-directory:conv-1:msg-1"' in metrics
    assert 'correlation_id="corr-teams-2"' in metrics
    assert 'purpose="Classify Teams turn for governed information handling"' in metrics
    assert 'capability="conversation.classify"' in metrics
    assert 'telemetry_quality="inferred"' in metrics
    assert "never-export-classifier-prompt" not in metrics
    assert "never-export-token" not in metrics
    assert "never-export-object" not in metrics
    assert "never-export-authorization" not in metrics
    assert "tenant-secret" not in metrics
    assert "object-secret" not in metrics
