from __future__ import annotations

import importlib.util
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def load_exporter():
    path = Path(__file__).resolve().parents[1] / "usage_exporter.py"
    spec = importlib.util.spec_from_file_location("jason_usage_exporter", path)
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
    entries = [
        {
            "entry_id": "entry-1",
            "context": {"organization_id": "aot"},
            "provider": "openai",
            "model": "gpt-5-nano",
            "outcome": "completed",
            "usage_source": "provider_reported",
            "tokens": {
                "input_tokens": 100,
                "cached_input_tokens": 20,
                "output_tokens": 50,
                "reasoning_tokens": 5,
                "total_tokens": 150,
            },
            "cost": {
                "provider_reported_cost": None,
                "calculated_cost": "0.10000000",
                "currency": "USD",
            },
            "completed_at": "2026-09-09T13:00:00+00:00",
            "metadata": {"api_key": "must-not-leak", "prompt": "private"},
        },
        {
            "entry_id": "entry-2",
            "context": {"organization_id": "aot"},
            "provider": "openai",
            "model": "gpt-5-nano",
            "outcome": "completed",
            "usage_source": "unknown",
            "tokens": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "cost": {
                "provider_reported_cost": "0.02000000",
                "calculated_cost": "0.03000000",
                "currency": "USD",
            },
            "completed_at": "2026-09-08T12:00:00+00:00",
        },
        {
            "entry_id": "other-org",
            "context": {"organization_id": "client-x"},
            "provider": "openai",
            "model": "gpt-5-nano",
            "outcome": "completed",
            "usage_source": "provider_reported",
            "tokens": {"total_tokens": 9999},
            "cost": {"calculated_cost": "99.00", "currency": "USD"},
            "completed_at": "2026-09-09T13:30:00+00:00",
        },
    ]
    for entry in entries:
        organization = entry["context"]["organization_id"]
        connection.execute(
            "INSERT INTO model_usage_entries VALUES (?, ?, ?, ?)",
            (
                entry["entry_id"],
                organization,
                "attempt-" + entry["entry_id"],
                json.dumps(entry),
            ),
        )
    adjustment = {
        "adjustment_id": "adj-1",
        "original_entry_id": "entry-1",
        "organization_id": "aot",
        "reason": "billing reconciliation",
        "created_at": "2026-09-09T13:30:00+00:00",
        "replacement_tokens": None,
        "replacement_cost": {
            "provider_reported_cost": "0.12000000",
            "calculated_cost": "0.10000000",
            "currency": "USD",
        },
        "authoritative_reference": "safe-ref",
    }
    connection.execute(
        "INSERT INTO model_usage_adjustments VALUES (?, ?, ?, ?)",
        ("adj-1", "entry-1", "aot", json.dumps(adjustment)),
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
    rows = [
        ("ev1", "exec1", "user-al", "endpoint.device.search", "2026-09-09T13:10:00+00:00"),
        ("ev2", "exec2", "user-al", "endpoint.device.read", "2026-09-09T13:20:00+00:00"),
        ("ev3", "exec3", "user-lori", "management.site.search", "2026-09-09T13:30:00+00:00"),
    ]
    for event_id, execution_id, principal_id, capability, occurred_at in rows:
        payload = {
            "execution_id": execution_id,
            "correlation_id": "corr-" + event_id,
            "principal_id": principal_id,
            "organization_id": "aot",
            "capability_name": capability,
            "stage": "received",
            "requester_kind": "human",
            "token": "never-export-this",
        }
        connection.execute(
            """
            INSERT INTO orchestration_events VALUES (?, '1.0', 'orchestration.request.received',
                ?, ?, 'aot', ?, ?, 'received', ?, ?)
            """,
            (
                event_id,
                execution_id,
                "corr-" + event_id,
                principal_id,
                capability,
                json.dumps(payload),
                occurred_at,
            ),
        )
    connection.commit()
    connection.close()


def create_bindings_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE microsoft_identity_bindings (
            microsoft_tenant_id TEXT NOT NULL,
            microsoft_object_id TEXT NOT NULL,
            jason_identity_id TEXT NOT NULL,
            client_id TEXT,
            email_address TEXT,
            status TEXT NOT NULL,
            PRIMARY KEY (microsoft_tenant_id, microsoft_object_id)
        );
        """
    )
    connection.execute(
        "INSERT INTO microsoft_identity_bindings VALUES ('tenant', 'oid-al', 'user-al', NULL, 'al@teamaot.com', 'active')"
    )
    connection.execute(
        "INSERT INTO microsoft_identity_bindings VALUES ('tenant', 'oid-lori', 'user-lori', NULL, 'lori@teamaot.com', 'active')"
    )
    connection.commit()
    connection.close()


def test_metrics_aggregate_cost_and_authenticated_users(tmp_path):
    module = load_exporter()
    module.MODEL_USAGE_DB = tmp_path / "model.sqlite3"
    module.ORCHESTRATION_EVENTS_DB = tmp_path / "events.sqlite3"
    module.IDENTITY_BINDINGS_DB = tmp_path / "bindings.sqlite3"
    create_model_db(module.MODEL_USAGE_DB)
    create_events_db(module.ORCHESTRATION_EVENTS_DB)
    create_bindings_db(module.IDENTITY_BINDINGS_DB)

    metrics = module.render_metrics(datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc))

    assert 'jason_usage_source_available{source="model_usage"} 1' in metrics
    assert 'jason_model_cost_usd{window="24h"} 0.12000000' in metrics
    assert 'jason_model_cost_usd{window="month_to_date"} 0.14000000' in metrics
    assert 'jason_model_attempts{window="24h"} 1' in metrics
    assert 'jason_model_unknown_usage_attempts{window="month_to_date"} 1' in metrics
    assert "jason_governed_requests_24h 3" in metrics
    assert "jason_active_users_24h 2" in metrics
    assert 'identity_id="user-al",email="al@teamaot.com",requester_kind="human"} 2' in metrics
    assert 'identity_id="user-lori",email="lori@teamaot.com",requester_kind="human"} 1' in metrics
    assert 'capability="endpoint.device.read"} 1' in metrics
    assert "99.00" not in metrics
    assert "must-not-leak" not in metrics
    assert "never-export-this" not in metrics
    assert "private" not in metrics


def test_missing_databases_fail_closed_without_creating_files(tmp_path):
    module = load_exporter()
    module.MODEL_USAGE_DB = tmp_path / "missing-model.sqlite3"
    module.ORCHESTRATION_EVENTS_DB = tmp_path / "missing-events.sqlite3"
    module.IDENTITY_BINDINGS_DB = tmp_path / "missing-bindings.sqlite3"

    metrics = module.render_metrics(datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc))

    assert 'jason_usage_source_available{source="model_usage"} 0' in metrics
    assert 'jason_usage_source_available{source="orchestration_events"} 0' in metrics
    assert 'jason_usage_source_available{source="identity_bindings"} 0' in metrics
    assert "jason_model_cost_usd" in metrics
    assert "jason_active_users_24h 0" in metrics
    assert not module.MODEL_USAGE_DB.exists()
    assert not module.ORCHESTRATION_EVENTS_DB.exists()
    assert not module.IDENTITY_BINDINGS_DB.exists()
