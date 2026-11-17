"""Stage C non-HTTP worker composition regression tests (offline only)."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from jason_runtime.composition import (
    TicketWorkerComponentRuntime, build_runtime_application,
)
from jason_runtime.maintenance_process import ticket_worker_runtime_settings
from test_composition import _settings


def test_ticket_profile_never_constructs_teams_http_or_auxiliary_stores(tmp_path):
    configured=replace(
        _settings(tmp_path),
        autonomy_worker_enabled=True,
        autonomy_worker_db=tmp_path/"ticket-core.sqlite3",
        autonomy_promotion_db=tmp_path/"autonomy-promotion.sqlite3",
        autonomy_targeted_wake_db=tmp_path/"targeted-wakes.sqlite3",
    )
    worker=build_runtime_application(
        ticket_worker_runtime_settings(configured),
        maintenance_profile="ticket_worker",
    )
    assert isinstance(worker, TicketWorkerComponentRuntime)
    assert worker.maintenance is not None
    assert not hasattr(worker,"ingress")
    assert not hasattr(worker,"dispatch")
    assert not hasattr(worker,"identity_binder")
    assert not hasattr(worker,"universal_approval_handler")

    # The general HTTP runtime constructor used to create these stores
    # even for a ticket-only process. They are not needed by this child.
    for name in (
        "continuation.sqlite3",
        "replay.sqlite3",
        "security.sqlite3",
        "dynamic-conversation-context.sqlite3",
        "universal-approvals.sqlite3",
        "mobile-release-approvals.sqlite3",
    ):
        assert not (tmp_path/name).exists(), name


def test_ticket_profile_durable_state_budget_contains_no_http_or_pm_db(tmp_path):
    """Fail on new worker dependencies before allowing any production mount."""
    configured=replace(
        _settings(tmp_path),
        autonomy_worker_enabled=True,
        autonomy_worker_db=tmp_path/"ticket-core.sqlite3",
        autonomy_promotion_db=tmp_path/"promotion.sqlite3",
        autonomy_targeted_wake_db=tmp_path/"targeted.sqlite3",
    )
    before={p.name for p in tmp_path.iterdir() if p.is_file()}
    build_runtime_application(
        ticket_worker_runtime_settings(configured),
        maintenance_profile="ticket_worker",
    )
    created={p.name for p in tmp_path.iterdir() if p.is_file()}-before
    databases={x for x in created if x.endswith(".sqlite3")}
    assert databases == {
        "authority.sqlite3", "bindings.sqlite3", "client-boundaries.sqlite3",
        "events.sqlite3", "governed-execution.sqlite3", "promotion.sqlite3",
        "reflection.sqlite3", "resolution-memory.sqlite3", "targeted.sqlite3",
        "ticket-core.sqlite3", "ticket-split.sqlite3",
    }
    assert all(not x.endswith(".db") for x in created)
    assert all(x.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm"))
               for x in created)


def test_ticket_only_component_does_not_activate_auxiliary_approval_workers(
    tmp_path,monkeypatch,
):
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED","false")
    settings=replace(
        _settings(tmp_path),
        autonomy_worker_enabled=True,
        autonomy_worker_db=tmp_path/"ticket-work.sqlite3",
        autonomy_promotion_db=tmp_path/"promotions.sqlite3",
        autonomy_targeted_wake_db=tmp_path/"wakes.sqlite3",
    )
    from jason_runtime.autonomy_teams_notification_maintenance import (
        TicketOwnerNotificationMaintenance,
    )
    component=build_runtime_application(
        ticket_worker_runtime_settings(settings),
        maintenance_profile="ticket_worker",
    )
    assert isinstance(component,TicketWorkerComponentRuntime)
    assert not any(isinstance(item,TicketOwnerNotificationMaintenance)
                   for item in component.maintenance.services)
    assert len(component.maintenance.services)==2


def test_ticket_worker_disabled_profile_denied_without_maintenance_start(tmp_path):
    settings=replace(
        _settings(tmp_path),
        autonomy_worker_enabled=False,
        autonomy_worker_db=tmp_path/"ticket-work.sqlite3",
    )
    with pytest.raises(RuntimeError,match="TICKET_CORE_WORKER_PROFILE_DISABLED"):
        build_runtime_application(settings,maintenance_profile="ticket_worker")
