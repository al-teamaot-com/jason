from types import SimpleNamespace

from jason_mcp import server


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
        '[{"uid":"component-dns","name":"Get-DNS Settings AOT Ver 06042025-1","approval_mode":"standing_safe"},'
        '{"uid":"component-edr","name":"Check Datto EDR/AV Status AOT Ver 12122025-1","approval_mode":"standing_safe"},'
        '{"uid":"component-reboot","name":"Scheduled Reboot AOT Ver 12112025-1","approval_mode":"per_run"}]',
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
                output={"data": {"status": "accepted"}},
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
        lambda: ("person-al", "aot", "entra-oauth-bearer", None),
    )

    return approvals, orchestrator_calls


def remediation_review(target: str, *, reboot: bool = False):
    return {"decision": "recommend", "target_id": target,
            "problem": "Endpoint requires targeted repair based on verified diagnostic evidence.",
            "evidence_refs": ["corr_mcp_ticket_read_diagnostic"],
            "expected_improvement": "Restore healthy endpoint operation without unnecessary changes.",
            "verification": "Reread endpoint health and confirm the reported error is cleared.",
            "narrower_options": ([{"action": "Restart only the affected service",
                                  "disposition": "attempted_failed",
                                  "evidence_refs": ["evidence://diagnostic/failed-restart"]}]
                                if reboot else [])}


def test_standing_safe_needs_no_explicit_per_run_approval(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "device-123",
            "component_uid": "component-dns",
        },
    )

    assert result["status"] == "succeeded"
    assert len(calls) == 1
    assert len(approvals) == 1
    assert approvals[0].decided_by == "policy:datto-standing-safe"


def test_per_run_rejected_before_orchestrator_without_explicit_approval(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": "component-reboot",
        },
    )

    assert result["status"] == "rejected"
    assert "REMEDIATION_ASSESSMENT_REQUIRED" in result["reason_codes"]
    assert approvals == []
    assert calls == []


def test_per_run_proceeds_when_current_technician_instruction_is_carried_as_approval(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": "component-reboot",
            "jason_remediation_review": remediation_review("other-managed-device", reboot=True),
        },
        explicit_approval=True,
    )

    assert result["status"] == "succeeded"
    assert len(calls) == 1
    assert len(approvals) == 1
    assert approvals[0].decided_by == "person-al"


def test_caller_cannot_override_server_approval_mode(monkeypatch):
    set_scope(monkeypatch)

    result = server._canonicalize_governed_action_arguments(
        "automation.component.execute",
        {
            "device_uid": "device-123",
            "component_uid": "component-reboot",
            "approval_mode": "standing_safe",
        },
    )

    assert "approval_mode" not in result
    selected = server.resolve_datto_component(
        server.configured_datto_components(),
        component_uid=result["component_uid"],
        component_name=result["component_name"],
    )
    assert selected.approval_mode == "per_run"


LINUX_SHELL_UID = "bc7c4531-6869-4658-b1d6-7639a477045e"
LINUX_SHELL_NAME = "Run Ad Hoc Command (Shell) [MAC] [LIN]"


def set_linux_worker_scope(monkeypatch):
    set_scope(monkeypatch)
    monkeypatch.setattr(
        server,
        "_resolve_live_datto_component_name",
        lambda name: (LINUX_SHELL_UID, LINUX_SHELL_NAME),
    )
    monkeypatch.setenv(
        "JASON_DATTO_COMPONENT_EXECUTION_COMPONENTS_JSON",
        '[{"uid":"' + LINUX_SHELL_UID + '","name":"' + LINUX_SHELL_NAME + '","approval_mode":"standing_safe"}]',
    )


def test_linux_worker_requires_server_enrollment(monkeypatch):
    set_linux_worker_scope(monkeypatch)
    monkeypatch.delenv("JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID", raising=False)
    try:
        server._canonicalize_governed_action_arguments(
            "automation.component.execute",
            {"device_uid": "claw2", "component_name": LINUX_SHELL_NAME, "variables": {"usrInput": "uname -srm"}},
        )
    except ValueError as exc:
        assert str(exc) == "DATTO_LINUX_SHELL_WORKER_TARGET_NOT_APPROVED"
    else:
        raise AssertionError("Linux shell missing enrolled host was allowed")


def test_linux_worker_denies_other_managed_devices(monkeypatch):
    set_linux_worker_scope(monkeypatch)
    monkeypatch.setenv("JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID", "claw2")
    try:
        server._canonicalize_governed_action_arguments(
            "automation.component.execute",
            {"device_uid": "production-claw", "component_name": LINUX_SHELL_NAME, "variables": {"usrInput": "uname -srm"}},
        )
    except ValueError as exc:
        assert str(exc) == "DATTO_LINUX_SHELL_WORKER_TARGET_NOT_APPROVED"
    else:
        raise AssertionError("Linux shell targeted a non-enrolled host")


def test_linux_worker_bound_to_exact_per_run_permission(monkeypatch):
    set_linux_worker_scope(monkeypatch)
    monkeypatch.setenv("JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID", "claw2")
    _, calls = install_runtime(monkeypatch)
    before_approval = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "claw2", "component_name": LINUX_SHELL_NAME, "variables": {"usrInput": "uname -srm"}},
    )
    assert before_approval["status"] == "rejected"
    assert "REMEDIATION_ASSESSMENT_REQUIRED" in before_approval["reason_codes"]
    assert calls == []
    with_approval = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "claw2", "component_name": LINUX_SHELL_NAME, "variables": {"usrInput": "uname -srm"},
                   "jason_remediation_review": remediation_review("claw2")},
        explicit_approval=True,
    )
    assert with_approval["status"] == "succeeded"
    assert len(calls) == 1


def test_linux_worker_has_separate_server_scope_without_legacy_catalog_entry(monkeypatch):
    set_scope(monkeypatch)
    monkeypatch.setattr(
        server,
        "_resolve_live_datto_component_name",
        lambda name: (LINUX_SHELL_UID, LINUX_SHELL_NAME),
    )
    monkeypatch.setenv("JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID", "claw2")
    # The Desktop catalog intentionally has no Linux shell component.
    assert all(
        component.uid != LINUX_SHELL_UID
        for component in server.configured_datto_components()
    )
    result = server._canonicalize_governed_action_arguments(
        "automation.component.execute",
        {"device_uid": "claw2", "component_name": LINUX_SHELL_NAME,
         "device_class": "Desktop",
         "variables": {"usrInput": "uname -srm"}},
    )
    assert result["device_uid"] == "claw2"
    assert result["allowlist_name"] == "aot-approved-linux-worker"
    assert result["device_class"] == "Server"
    assert result["component_uid"] == LINUX_SHELL_UID
    _, calls = install_runtime(monkeypatch)
    unapproved = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "claw2", "component_name": LINUX_SHELL_NAME,
                   "variables": {"usrInput": "uname -srm"}},
    )
    assert unapproved["status"] == "rejected"
    assert "REMEDIATION_ASSESSMENT_REQUIRED" in unapproved["reason_codes"]
    assert calls == []
    approved = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={"device_uid": "claw2", "component_name": LINUX_SHELL_NAME,
                   "variables": {"usrInput": "uname -srm"},
                   "jason_remediation_review": remediation_review("claw2")},
        explicit_approval=True,
    )
    assert approved["status"] == "succeeded"
    assert len(calls) == 1


def test_separate_worker_scope_does_not_change_desktop_diagnostics(monkeypatch):
    set_scope(monkeypatch)
    monkeypatch.setenv("JASON_DATTO_LINUX_SHELL_WORKER_DEVICE_UID", "claw2")
    result = server._canonicalize_governed_action_arguments(
        "automation.component.execute",
        {"device_uid": "device-123", "component_uid": "component-dns"},
    )
    assert result["allowlist_name"] == "AOT governed diagnostic pilot"
    assert result["device_class"] == "Desktop"


def test_user_approval_does_not_override_jasons_negative_remediation_judgment(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)
    review = remediation_review("other-managed-device", reboot=True)
    review["decision"] = "do_not_run"
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": "component-reboot",
            "jason_remediation_review": review,
        },
        explicit_approval=True,
    )
    assert result["status"] == "rejected"
    assert result["error_code"] == "REMEDIATION_ACTION_NOT_JUSTIFIED"
    assert "REMEDIATION_NOT_RECOMMENDED_BY_JASON" in result["reason_codes"]
    assert approvals == [] and calls == []


def test_reboot_refused_for_print_failure_with_viable_spooler_restart(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)
    review = remediation_review("other-managed-device", reboot=True)
    review["problem"] = "Print Spooler service stopped and the print queue cannot print."
    review["narrower_options"][0]["disposition"] = "viable"
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": "component-reboot",
            "jason_remediation_review": review,
        },
        explicit_approval=True,
    )
    assert result["status"] == "rejected"
    assert "LESS_DISRUPTIVE_EFFECTIVE_ACTION_AVAILABLE" in result["reason_codes"]
    assert approvals == [] and calls == []


def test_exact_technician_approved_reboot_with_failed_narrower_remedy_has_bound_policy(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)
    review = remediation_review("other-managed-device", reboot=True)
    review["problem"] = "Printer queue still fails after verified targeted spooler restart."
    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "other-managed-device",
            "component_uid": "component-reboot",
            "jason_remediation_review": review,
        },
        explicit_approval=True,
    )
    assert result["status"] == "succeeded"
    assert len(calls) == 1 and len(approvals) == 1
    assert not any(key == "jason_remediation_review" for key in calls[0].arguments)
    assert any(value.startswith("least-disruptive-remediation-v1:")
               for value in calls[0].policy_ids)
