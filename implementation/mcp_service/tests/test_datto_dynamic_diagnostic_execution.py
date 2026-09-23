from types import SimpleNamespace

import pytest

from jason_mcp import server


UID = "8a1c153c-feee-41c5-9c9b-58a48e0214fe"
NAME = "Run Ad Hoc Command (PowerShell 2-5) [WIN]"
TARGET = "device-123"
ALLOWLIST = "AOT governed diagnostic pilot"


def set_scope(monkeypatch):
    monkeypatch.setenv(
        "JASON_DATTO_COMPONENT_EXECUTION_ALLOWLIST_NAME",
        ALLOWLIST,
    )
    monkeypatch.setenv(
        "JASON_DATTO_COMPONENT_EXECUTION_DEVICE_UID",
        TARGET,
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

    def resolve_live_component(requested_name):
        if str(requested_name).strip().casefold() != NAME.casefold():
            raise ValueError("DATTO_COMPONENT_NAME_MISMATCH")
        return (
            UID,
            NAME,
            (
                {
                    "name": "usrInput",
                    "variable_type": "string",
                    "required": False,
                    "maximum_length": 20_000,
                },
            ),
        )

    monkeypatch.setattr(
        server,
        "_resolve_live_datto_component_name",
        resolve_live_component,
    )
    monkeypatch.setattr(
        server,
        "_resolve_live_datto_endpoint_target",
        lambda device_uid: "Desktop",
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
        lambda: (
            "person-al",
            "aot",
            "entra-oauth-bearer",
            None,
        ),
    )

    return approvals, orchestrator_calls


def execute(
    command,
    *,
    extra_arguments=None,
    variables=None,
    explicit_approval=False,
):
    arguments = {
        "device_uid": TARGET,
        "component_uid": UID,
        "component_name": NAME,
        "variables": (
            {"usrInput": command}
            if variables is None
            else variables
        ),
    }
    arguments.update(extra_arguments or {})
    return server._governed_execute(
        capability_name="automation.component.execute",
        arguments=arguments,
        explicit_approval=explicit_approval,
    )


@pytest.mark.parametrize(
    "command",
    [
        "Get-Service -Name 'HUNTAgent'",
        "Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object Caption,Version,LastBootUpTime",
        "Test-NetConnection 1.1.1.1 -Port 443",
        "ping.exe 1.1.1.1 -n 2 -w 1000",
    ],
)
def test_dynamic_safe_diagnostics_receive_policy_standing_safe(
    monkeypatch,
    command,
):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = execute(
        command,
        extra_arguments={"approval_mode": "per_run"},
    )

    assert result["status"] == "succeeded"
    assert len(approvals) == 1
    assert len(calls) == 1

    approval = approvals[0]
    assert approval.requested_by == "person-al"
    assert approval.decided_by == "policy:datto-powershell-readonly"
    assert approval.decided_by != "person-al"

    governed_request = calls[0]
    assert governed_request.arguments == {
        "allowlist_name": ALLOWLIST,
        "device_uid": TARGET,
        "device_class": "Desktop",
        "component_uid": UID,
        "component_name": NAME,
        "variables": {"usrInput": command},
        "variable_policies": [
            {
                "name": "usrInput",
                "variable_type": "string",
                "required": False,
                "maximum_length": 20_000,
            },
        ],
    }
    assert "approval_mode" not in governed_request.arguments
    assert governed_request.budget.maximum_attempts == 1


@pytest.mark.parametrize(
    "command",
    [
        "Start-Service HUNTAgent",
        "Stop-Service HUNTAgent",
        "Restart-Service HUNTAgent",
        "Set-ItemProperty HKLM:\\Software\\AOT -Name Test -Value 1",
        r"reg.exe add HKLM\Software\AOT /v Test /d 1",
        "ipconfig /flushdns",
        "netsh wlan delete profile name=AlphaGuest",
        "cmd.exe /c whoami",
        r"C:\Temp\diagnostic.ps1",
        "Get-Service; Restart-Service HUNTAgent",
        r"Get-ItemProperty HKLM:\SAM\Domains\Account",
        r"reg.exe query HKLM\SECURITY\Policy\Secrets",
        "powershell.exe -EncodedCommand AAAA",
        "Invoke-Expression 'Get-Date'",
        "Get-SomethingNew -Name Example",
    ],
)
def test_unsafe_unknown_or_sensitive_commands_cannot_self_promote(
    monkeypatch,
    command,
):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = execute(
        command,
        extra_arguments={"approval_mode": "standing_safe"},
    )

    assert result["status"] == "approval_required"
    assert (
        "DATTO_POWERSHELL_COMMAND_APPROVAL_REQUIRED"
        in result["reason_codes"]
    )
    assert (
        "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED"
        in result["reason_codes"]
    )
    assert approvals == []
    assert calls == []


def test_unapproved_variable_cannot_receive_standing_safe(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = execute(
        "Get-Service HUNTAgent",
        variables={"otherInput": "Get-Service HUNTAgent"},
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "invalid_action_arguments"
    assert "DATTO_COMPONENT_VARIABLE_NOT_DECLARED" in result["reason_codes"]
    assert approvals == []
    assert calls == []


def test_extra_variable_cannot_receive_standing_safe(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = execute(
        "Get-Service HUNTAgent",
        variables={
            "usrInput": "Get-Service HUNTAgent",
            "otherInput": "ignored",
        },
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "invalid_action_arguments"
    assert "DATTO_COMPONENT_VARIABLE_NOT_DECLARED" in result["reason_codes"]
    assert approvals == []
    assert calls == []


def test_standing_safe_diagnostic_can_target_revalidated_managed_endpoint(
    monkeypatch,
):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = execute(
        "Get-Service HUNTAgent",
        extra_arguments={"device_uid": "different-device"},
    )

    assert result["status"] == "succeeded"
    assert len(approvals) == 1
    assert approvals[0].decided_by == "policy:datto-powershell-readonly"
    assert len(calls) == 1
    assert calls[0].arguments["device_uid"] == "different-device"
    assert calls[0].arguments["device_class"] == "Desktop"


def test_per_run_component_on_revalidated_target_requires_and_accepts_approval(
    monkeypatch,
):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    first = execute(
        "Restart-Service HUNTAgent",
        extra_arguments={"device_uid": "different-device"},
    )
    assert first["status"] == "approval_required"
    assert "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED" in first["reason_codes"]
    assert approvals == []
    assert calls == []

    second = execute(
        "Restart-Service HUNTAgent",
        extra_arguments={"device_uid": "different-device"},
        explicit_approval=True,
    )
    assert second["status"] == "succeeded"
    assert len(approvals) == 1
    assert approvals[0].decided_by == "person-al"
    assert len(calls) == 1
    assert calls[0].arguments["device_uid"] == "different-device"


def test_altered_component_uid_fails_before_authority_or_provider(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = execute(
        "Get-Service HUNTAgent",
        extra_arguments={"component_uid": "different-component"},
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "invalid_action_arguments"
    assert "DATTO_COMPONENT_IDENTITY_MISMATCH" in result["reason_codes"]
    assert approvals == []
    assert calls == []


def test_altered_component_name_fails_before_authority_or_provider(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = execute(
        "Get-Service HUNTAgent",
        extra_arguments={"component_name": "Run Some Other Component"},
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "invalid_action_arguments"
    assert "DATTO_COMPONENT_NAME_MISMATCH" in result["reason_codes"]
    assert approvals == []
    assert calls == []
