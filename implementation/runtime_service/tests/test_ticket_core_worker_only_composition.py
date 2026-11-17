"""Stage C non-HTTP worker composition regression tests (offline only)."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from jason_runtime.composition import (
    TicketWorkerComponentRuntime, _shadow_processes_targeted_wakes,
    build_runtime_application,
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


def test_ticket_settings_forbid_unrelated_schedulers_but_preserve_providers(tmp_path):
    configured=replace(
        _settings(tmp_path),
        autonomy_worker_enabled=True,
        autonomy_shadow_enabled=True,
        autonomy_review_enabled=True,
        playbook_approval_ingress_enabled=True,
        support_repair_autonomy_enabled=True,
        universal_approval_mode="enforced",
        universal_approval_worker_enabled=True,
        release_mobile_approval_mode="owner_reviewed",
        release_mobile_approval_worker_enabled=True,
        owner_uat_mode="nonexecuting_test_only",
        owner_uat_worker_enabled=True,
        drmm_recent_alert_reconciliation_enabled=True,
        windows_time_source_shadow_enabled=True,
        dynamic_conversation_enabled=True,
        conversation_experience_enabled=True,
        backup_net_enabled=True,
        dnsfilter_enabled=True,
        hosted_conversation_enabled=True,
    )
    scoped=ticket_worker_runtime_settings(configured)
    assert scoped.autonomy_worker_enabled is True
    for flag in (
        "autonomy_shadow_enabled","autonomy_review_enabled",
        "playbook_approval_ingress_enabled","support_repair_autonomy_enabled",
        "universal_approval_worker_enabled","release_mobile_approval_worker_enabled",
        "owner_uat_worker_enabled","drmm_recent_alert_reconciliation_enabled",
        "windows_time_source_shadow_enabled","dynamic_conversation_enabled",
        "conversation_experience_enabled",
    ):
        assert getattr(scoped,flag) is False,flag
    assert scoped.universal_approval_mode == "off"
    assert scoped.release_mobile_approval_mode == "off"
    assert scoped.owner_uat_mode == "off"
    assert scoped.backup_net_enabled is True
    assert scoped.dnsfilter_enabled is True
    assert scoped.hosted_semantics_enabled == configured.hosted_semantics_enabled
    assert scoped.hosted_conversation_enabled is False
    scoped.validate()


def test_external_hosting_never_leaves_targeted_wakes_to_auxiliary_shadow(tmp_path):
    base=replace(_settings(tmp_path),autonomy_worker_enabled=False)
    assert _shadow_processes_targeted_wakes(
        replace(base,ticket_worker_hosting="embedded")) is True
    assert _shadow_processes_targeted_wakes(
        replace(base,ticket_worker_hosting="external")) is False
    assert _shadow_processes_targeted_wakes(
        replace(base,ticket_worker_hosting="external",autonomy_worker_enabled=True)
    ) is False
