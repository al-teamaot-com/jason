"""Standing-safe diagnostic exemption requires an exact reviewed Datto identity.

These tests do not reach Datto. The mock authority and orchestrator intentionally
track whether a request would dispatch without per-run approval.
"""
import pytest

from jason_mcp import server
from test_datto_component_approval_policy import install_runtime, set_scope


APPROVED_IDENTITIES = (
    ("79943f0c-e614-4fcc-a5da-e396feab0a34", "Windows Diagnostic Snapshot - AOT"),
    ("4e9d59fb-440a-460b-9107-40f3954890fd", "Disk Space Analysis - AOT"),
    ("c259df3f-a6a2-4931-bf48-b6659846e9b1", "Network and DNS Diagnostics - AOT"),
)
FINGERPRINT = "b" * 64


@pytest.fixture(autouse=True)
def isolated_governed_ledger(monkeypatch, tmp_path):
    # The CI runner must never use the host's protected production ledger.
    monkeypatch.setenv("JASON_GOVERNED_EXECUTION_DB", str(tmp_path / "governed-exec.sqlite3"))
    server._governed_execution_ledger.cache_clear()
    yield
    server._governed_execution_ledger.cache_clear()


def setup_reviewed(monkeypatch, uid, name, **overrides):
    set_scope(monkeypatch)
    component = server.DattoApprovedComponent(
        uid=uid,
        name=name,
        approval_mode=overrides.get("mode", "standing_safe"),
        approval_source=overrides.get("source", "durable_registry"),
        metadata_fingerprint=overrides.get("fingerprint", FINGERPRINT),
    )
    monkeypatch.setattr(server, "configured_datto_components", lambda: (component,))
    monkeypatch.setattr(server, "_active_datto_execution_components", lambda: (component,))
    monkeypatch.setattr(server, "_resolve_live_datto_component_uid", lambda requested: (uid, name))
    monkeypatch.setattr(server, "_resolve_live_datto_component_record",
                        lambda requested: {"resource_id": uid, "name": name})
    monkeypatch.setattr(server, "component_metadata_fingerprint",
                        lambda record: overrides.get("live_fingerprint", FINGERPRINT))
    return component


@pytest.mark.parametrize("uid,name", APPROVED_IDENTITIES)
def test_reviewed_owner_standing_safe_runs_without_technician_approval(monkeypatch, uid, name):
    setup_reviewed(monkeypatch, uid, name)
    approvals, executions = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "device-123", "component_uid": uid, "variables": {}},
    )
    assert result["status"] == "succeeded"
    assert len(executions) == 1
    assert len(approvals) == 1
    assert approvals[0].decided_by == "policy:datto-standing-safe"


def test_unreviewed_name_cannot_inherit_passive_exemption(monkeypatch):
    uid, name = APPROVED_IDENTITIES[0]
    setup_reviewed(monkeypatch, uid, "Unreviewed Windows Diagnostic - AOT")
    approvals, executions = install_runtime(monkeypatch)
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "device-123", "component_uid": uid, "variables": {}},
    )
    assert result["error_code"] == "REMEDIATION_ACTION_NOT_JUSTIFIED"
    assert approvals == executions == []


def test_unreviewed_uid_cannot_inherit_passive_exemption(monkeypatch):
    uid, name = APPROVED_IDENTITIES[0]
    setup_reviewed(monkeypatch, "unreviewed-uid", name)
    approvals, executions = install_runtime(monkeypatch)
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "device-123", "component_uid": "unreviewed-uid", "variables": {}},
    )
    assert result["error_code"] == "REMEDIATION_ACTION_NOT_JUSTIFIED"
    assert approvals == executions == []


@pytest.mark.parametrize("changes", [
    {"mode": "per_run"},
    {"source": "server_config"},
    {"fingerprint": None},
    {"fingerprint": FINGERPRINT, "live_fingerprint": "a" * 64},
])
def test_unapproved_or_stale_identity_fails_closed(monkeypatch, changes):
    uid, name = APPROVED_IDENTITIES[0]
    setup_reviewed(monkeypatch, uid, name, **changes)
    approvals, executions = install_runtime(monkeypatch)
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "device-123", "component_uid": uid, "variables": {}},
    )
    assert result["status"] == "rejected"
    assert approvals == executions == []


def test_variables_require_separate_review_even_for_approved_diagnostic(monkeypatch):
    uid, name = APPROVED_IDENTITIES[2]
    component = setup_reviewed(monkeypatch, uid, name)
    assert not server._is_reviewed_aot_passive_diagnostic(component, "standing_safe",
                                                           {"TargetHost": "test.local"})
    approvals, executions = install_runtime(monkeypatch)
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "device-123", "component_uid": uid,
                   "variables": {"TargetHost": "test.local"}},
    )
    assert result["status"] == "rejected"
    assert approvals == executions == []


def test_ad_hoc_runner_cannot_inherit_passive_exemption():
    component = server.DattoApprovedComponent(
        uid=server.DATTO_AD_HOC_POWERSHELL_UID,
        name=server.DATTO_AD_HOC_POWERSHELL_NAME,
        approval_mode="standing_safe",
        approval_source="durable_registry",
        metadata_fingerprint=FINGERPRINT,
    )
    assert not server._is_reviewed_aot_passive_diagnostic(component, "standing_safe", {})
