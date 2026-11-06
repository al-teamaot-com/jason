from types import SimpleNamespace

from jason_mcp import server


UID = "8a1c153c-feee-41c5-9c9b-58a48e0214fe"
NAME = "Run Ad Hoc Command (PowerShell 2-5) [WIN]"


def set_scope(monkeypatch):
    monkeypatch.setattr(
        server,
        "_verify_managed_datto_component_target",
        lambda value: str(value).strip(),
    )
    monkeypatch.setenv(
        "JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME",
        "AOT governed diagnostic pilot",
    )
    monkeypatch.setenv(
        "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID",
        "device-123",
    )
    monkeypatch.setenv(
        "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_CLASS",
        "Desktop",
    )
    monkeypatch.setenv(
        "JASON_DATTO_COMPONENT_EXECUTION_COMPONENTS_JSON",
        (
            '[{"uid":"'
            + UID
            + '","name":"'
            + NAME
            + '","approval_mode":"per_run"}]'
        ),
    )


def install_runtime(monkeypatch):
    approvals = []
    orchestrator_calls = []

    class ApprovalRepository:
        def put(self, record):
            approvals.append(record)

    class Authority:
        def __init__(self):
            self.approvals = ApprovalRepository()

        def evaluate(self, request):
            if request.approval_id:
                return SimpleNamespace(
                    outcome=server.AuthorityOutcome.ALLOWED,
                    reason_codes=("APPROVAL_VALID",),
                    execution_context=SimpleNamespace(
                        context_id="ctx-approved",
                        approval_required=True,
                    ),
                )

            return SimpleNamespace(
                outcome=server.AuthorityOutcome.APPROVAL_REQUIRED,
                reason_codes=("APPROVAL_REQUIRED",),
                execution_context=None,
            )

    capability = SimpleNamespace(
        metadata={
            "mcp_action_enabled": "true",
            "conversation_authenticated_imperative_is_approval": "false",
        },
        approval=SimpleNamespace(required=True),
        risk_level=SimpleNamespace(value="high"),
    )

    class Capabilities:
        def get_current(self, *, capability_name):
            assert capability_name == "automation.component.execute"
            return capability

    class Orchestrator:
        def execute(self, request):
            orchestrator_calls.append(request)

            return SimpleNamespace(
                status=SimpleNamespace(value="succeeded"),
                stage=SimpleNamespace(value="completed"),
                capability_name="automation.component.execute",
                provider_id="datto_rmm_component_execution",
                reason_codes=(),
                error_code=None,
                correlation_id=request.correlation_id,
                attempts=1,
                output={
                    "data": {
                        "status": "accepted",
                    }
                },
            )

    monkeypatch.setattr(
        server,
        "_runtime",
        lambda: SimpleNamespace(
            capabilities=Capabilities(),
            identity_authority=Authority(),
            governed_orchestrator=Orchestrator(),
        ),
    )

    monkeypatch.setattr(
        server,
        "_authenticated_write_identity",
        lambda: (
            "person-al",
            "aot",
            "entra-oauth-bearer",
            None,
        ),
    )

    return approvals, orchestrator_calls


def remediation_review(target: str):
    return {
        "decision": "recommend", "target_id": target,
        "problem": "Endpoint protection service is stopped and not responding to user requests.",
        "evidence_refs": ["corr_mcp_service_status_read"],
        "expected_improvement": "Start only the stopped protection service to restore protection.",
        "verification": "Reread the protection service state and EDR status after the action.",
        "narrower_options": [],
    }


def test_read_only_powershell_needs_no_technician_approval(
    monkeypatch,
):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": UID,
            "variables": {
                "usrInput": (
                    "Get-Service -Name "
                    "'EndpointProtectionService'"
                ),
            },
        },
    )

    assert result["status"] == "succeeded"
    assert len(calls) == 1
    assert len(approvals) == 1
    assert (
        approvals[0].decided_by
        == "policy:datto-powershell-readonly"
    )


def test_mutating_powershell_requires_explicit_approval(
    monkeypatch,
):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": UID,
            "variables": {
                "usrInput": (
                    "Start-Service -Name "
                    "'EndpointProtectionService'"
                ),
            },
        },
    )

    assert result["status"] == "rejected"
    assert "REMEDIATION_ASSESSMENT_REQUIRED" in result["reason_codes"]
    assert approvals == []
    assert calls == []


def test_mutating_powershell_runs_after_explicit_approval(
    monkeypatch,
):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": UID,
            "variables": {
                "usrInput": (
                    "Start-Service -Name "
                    "'EndpointProtectionService'"
                ),
            },
            "jason_remediation_review": remediation_review("other-managed-device"),
        },
        explicit_approval=True,
    )

    assert result["status"] == "succeeded"
    assert len(calls) == 1
    assert len(approvals) == 1
    assert approvals[0].decided_by == "person-al"


def test_spooler_service_repair_requires_approval_but_avoids_reboot(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)
    review = remediation_review("other-managed-device")
    review["problem"] = "Print Spooler is stopped and print requests remain queued."
    review["expected_improvement"] = "Restart the Print Spooler only, without rebooting the PC."
    review["verification"] = "Read spooler status and confirm queued print job completes."
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": UID,
            "variables": {"usrInput": "Restart-Service Spooler"},
            "jason_remediation_review": review,
        },
        explicit_approval=True,
    )
    assert result["status"] == "succeeded"
    assert len(calls) == 1
    assert len(approvals) == 1
    assert calls[0].arguments["variables"]["usrInput"] == "Restart-Service Spooler"
    assert "jason_remediation_review" not in calls[0].arguments
