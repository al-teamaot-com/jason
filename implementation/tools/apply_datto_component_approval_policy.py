#!/usr/bin/env python3
"""Apply and validate Jason's server-controlled Datto approval policy.

This migration changes source/tests only. It performs no provider calls, does
not change grants/credentials, and does not deploy or restart services.

Approval modes are server-owned:
- standing_safe: exact non-disruptive diagnostic component; no separate
  per-run human approval is required.
- per_run: exact disruptive/state-changing component; current explicit
  technician approval is required before orchestration.
- unknown component or approval mode: fail closed.

The action caller cannot supply or override approval_mode.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class MigrationError(RuntimeError):
    pass


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise MigrationError(
            f"{path}: expected exactly one source match, found {count}"
        )
    write(path, content.replace(old, new, 1))


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise MigrationError(
            f"command failed with rc={completed.returncode}: {' '.join(command)}"
        )


def already_applied() -> bool:
    scope = read(
        "implementation/runtime_service/src/jason_runtime/datto_component_scope.py"
    )
    server = read("implementation/mcp_service/src/jason_mcp/server.py")
    return (
        'DATTO_APPROVAL_MODE_STANDING_SAFE = "standing_safe"' in scope
        and "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED" in server
        and "explicit_approval: bool = False" in server
    )


def patch_scope() -> None:
    path = "implementation/runtime_service/src/jason_runtime/datto_component_scope.py"

    replace_once(
        path,
        """DATTO_EXECUTION_COMPONENT_NAME_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME"
)

_MAX_COMPONENTS = 16
""",
        """DATTO_EXECUTION_COMPONENT_NAME_ENV = (
    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME"
)

DATTO_APPROVAL_MODE_STANDING_SAFE = "standing_safe"
DATTO_APPROVAL_MODE_PER_RUN = "per_run"
_VALID_APPROVAL_MODES = frozenset(
    {
        DATTO_APPROVAL_MODE_STANDING_SAFE,
        DATTO_APPROVAL_MODE_PER_RUN,
    }
)

_MAX_COMPONENTS = 16
""",
    )

    replace_once(
        path,
        """@dataclass(frozen=True, slots=True)
class DattoApprovedComponent:
    uid: str
    name: str
""",
        """@dataclass(frozen=True, slots=True)
class DattoApprovedComponent:
    uid: str
    name: str
    approval_mode: str = DATTO_APPROVAL_MODE_PER_RUN

    @property
    def requires_explicit_approval(self) -> bool:
        return self.approval_mode == DATTO_APPROVAL_MODE_PER_RUN
""",
    )

    replace_once(
        path,
        """def _normalize_component(uid: object, name: object) -> DattoApprovedComponent:
    normalized_uid = str(uid or "").strip()
    normalized_name = str(name or "").strip()
""",
        """def _normalize_component(
    uid: object,
    name: object,
    approval_mode: object = DATTO_APPROVAL_MODE_PER_RUN,
) -> DattoApprovedComponent:
    normalized_uid = str(uid or "").strip()
    normalized_name = str(name or "").strip()
    normalized_approval_mode = str(approval_mode or "").strip().casefold()
""",
    )

    replace_once(
        path,
        """    if (
        normalized_uid.casefold() in _FORBIDDEN_SCOPE_VALUES
        or normalized_name.casefold() in _FORBIDDEN_SCOPE_VALUES
    ):
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
        )

    return DattoApprovedComponent(
        uid=normalized_uid,
        name=normalized_name,
    )
""",
        """    if (
        normalized_uid.casefold() in _FORBIDDEN_SCOPE_VALUES
        or normalized_name.casefold() in _FORBIDDEN_SCOPE_VALUES
    ):
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"
        )

    if normalized_approval_mode not in _VALID_APPROVAL_MODES:
        raise DattoComponentScopeError(
            "DATTO_COMPONENT_EXECUTION_APPROVAL_MODE_INVALID"
        )

    return DattoApprovedComponent(
        uid=normalized_uid,
        name=normalized_name,
        approval_mode=normalized_approval_mode,
    )
""",
    )

    replace_once(
        path,
        '            if set(item) != {"uid", "name"}:\n',
        '            if set(item) != {"uid", "name", "approval_mode"}:\n',
    )

    replace_once(
        path,
        """                _normalize_component(
                    item.get("uid"),
                    item.get("name"),
                )
""",
        """                _normalize_component(
                    item.get("uid"),
                    item.get("name"),
                    item.get("approval_mode"),
                )
""",
    )


def patch_runtime() -> None:
    path = "implementation/runtime_service/src/jason_runtime/datto_component_execution.py"

    replace_once(
        path,
        """            "conversation_authenticated_imperative_is_approval": (
                "true"
            ),
            "pilot_scope": "aot_owner_exact_component_exact_endpoint",
""",
        """            "conversation_authenticated_imperative_is_approval": (
                "false"
            ),
            "component_approval_policy": (
                "server_classified_standing_safe_or_per_run"
            ),
            "pilot_scope": "aot_owner_exact_component_exact_endpoint",
""",
    )

    replace_once(
        path,
        "                    requires_per_run_approval=True,\n",
        """                    requires_per_run_approval=(
                        selected_component.requires_explicit_approval
                    ),
""",
    )


def patch_mcp_server() -> None:
    path = "implementation/mcp_service/src/jason_mcp/server.py"

    replace_once(
        path,
        """def _governed_execute(
    *,
    capability_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
""",
        """def _governed_execute(
    *,
    capability_name: str,
    arguments: Mapping[str, Any],
    explicit_approval: bool = False,
) -> dict[str, Any]:
""",
    )

    replace_once(
        path,
        """    execution_id = f"exec_mcp_action_{uuid4().hex}"
    correlation_id = f"corr_mcp_action_{uuid4().hex}"
""",
        """    datto_approval_mode: str | None = None

    if capability_name == "automation.component.execute":
        try:
            selected_component = resolve_datto_component(
                configured_datto_components(),
                component_uid=canonical_arguments.get("component_uid"),
                component_name=canonical_arguments.get("component_name"),
            )
        except ValueError as exc:
            return {
                "status": "rejected",
                "capability": capability_name,
                "error_code": "invalid_action_arguments",
                "reason_codes": [str(exc)],
            }

        datto_approval_mode = selected_component.approval_mode

    execution_id = f"exec_mcp_action_{uuid4().hex}"
    correlation_id = f"corr_mcp_action_{uuid4().hex}"
""",
    )

    replace_once(
        path,
        """    if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:
        imperative_approval = (
            str(
                metadata.get(
                    "conversation_authenticated_imperative_is_approval",
                    "",
                )
            ).casefold()
            == "true"
        )

        if not imperative_approval:
            return {
                "status": "approval_required",
                "capability": capability_name,
                "reason_codes": list(decision.reason_codes),
                "correlation_id": correlation_id,
            }

        approval_repository = getattr(
""",
        """    if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:
        approval_decided_by = principal

        if capability_name == "automation.component.execute":
            if datto_approval_mode == "standing_safe":
                imperative_approval = True
                approval_decided_by = "policy:datto-standing-safe"
            elif datto_approval_mode == "per_run":
                imperative_approval = explicit_approval is True

                if not imperative_approval:
                    return {
                        "status": "approval_required",
                        "capability": capability_name,
                        "reason_codes": [
                            "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED",
                            *list(decision.reason_codes),
                        ],
                        "correlation_id": correlation_id,
                    }
            else:
                return {
                    "status": "denied",
                    "capability": capability_name,
                    "reason_codes": [
                        "DATTO_COMPONENT_APPROVAL_MODE_INVALID",
                    ],
                    "correlation_id": correlation_id,
                }
        else:
            imperative_approval = (
                str(
                    metadata.get(
                        "conversation_authenticated_imperative_is_approval",
                        "",
                    )
                ).casefold()
                == "true"
            )

        if not imperative_approval:
            return {
                "status": "approval_required",
                "capability": capability_name,
                "reason_codes": list(decision.reason_codes),
                "correlation_id": correlation_id,
            }

        approval_repository = getattr(
""",
    )

    replace_once(
        path,
        "                decided_by=principal,\n",
        "                decided_by=approval_decided_by,\n",
    )

    replace_once(
        path,
        """        "write_authority": (
            "jason_exact_grant_plus_per_execution_approval"
            if write_enabled
            else None
        ),
""",
        """        "write_authority": (
            "jason_exact_grant_plus_server_governed_approval_policy"
            if write_enabled
            else None
        ),
        "datto_component_approval_policy": (
            "server_classified_standing_safe_or_per_run"
            if "automation.component.execute" in actions
            else None
        ),
""",
    )

    replace_once(
        path,
        """def execute_governed_capability(
    capability: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
""",
        """def execute_governed_capability(
    capability: str,
    arguments: dict[str, Any],
    explicit_approval: bool = False,
) -> dict[str, Any]:
""",
    )

    replace_once(
        path,
        """    Microsoft Entra authenticates the caller; Jason authority, approval policy,
    Central Orchestrator routing, provider isolation, attempt limits and audit
    remain authoritative.
""",
        """    Microsoft Entra authenticates the caller; Jason authority, approval policy,
    Central Orchestrator routing, provider isolation, attempt limits and audit
    remain authoritative. For server-classified Datto per_run components,
    explicit_approval must be true only after the authenticated technician has
    explicitly approved that exact execution. standing_safe classification is
    server-controlled and never accepted from action arguments.
""",
    )

    replace_once(
        path,
        """    return _governed_execute(
        capability_name=capability_name,
        arguments=dict(arguments or {}),
    )
""",
        """    return _governed_execute(
        capability_name=capability_name,
        arguments=dict(arguments or {}),
        explicit_approval=(explicit_approval is True),
    )
""",
    )


def write_scope_tests() -> None:
    path = "implementation/runtime_service/tests/test_datto_component_scope.py"
    write(
        path,
        '''import pytest

from jason_runtime.datto_component_scope import (
    DATTO_EXECUTION_COMPONENT_NAME_ENV,
    DATTO_EXECUTION_COMPONENT_UID_ENV,
    DATTO_EXECUTION_COMPONENTS_JSON_ENV,
    DattoComponentScopeError,
    configured_datto_components,
    resolve_datto_component,
)


def clear_component_env(monkeypatch):
    for name in (
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        DATTO_EXECUTION_COMPONENT_UID_ENV,
        DATTO_EXECUTION_COMPONENT_NAME_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def test_legacy_single_component_fallback_is_conservative_per_run(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(DATTO_EXECUTION_COMPONENT_UID_ENV, "component-1")
    monkeypatch.setenv(DATTO_EXECUTION_COMPONENT_NAME_ENV, "Diagnostic One")

    components = configured_datto_components()

    assert len(components) == 1
    assert components[0].uid == "component-1"
    assert components[0].name == "Diagnostic One"
    assert components[0].approval_mode == "per_run"
    assert components[0].requires_explicit_approval is True


def test_json_scope_is_authoritative_and_server_classified(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(DATTO_EXECUTION_COMPONENT_UID_ENV, "legacy-component")
    monkeypatch.setenv(DATTO_EXECUTION_COMPONENT_NAME_ENV, "Legacy Diagnostic")
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"},'
        '{"uid":"component-2","name":"Diagnostic Two","approval_mode":"per_run"}]',
    )

    components = configured_datto_components()

    assert [item.uid for item in components] == ["component-1", "component-2"]
    assert components[0].approval_mode == "standing_safe"
    assert components[0].requires_explicit_approval is False

    selected = resolve_datto_component(
        components,
        component_uid="component-2",
        component_name="Diagnostic Two",
    )
    assert selected.approval_mode == "per_run"
    assert selected.requires_explicit_approval is True


@pytest.mark.parametrize(
    "payload,reason",
    [
        ("not-json", "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"),
        ("[]", "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"),
        (
            '[{"uid":"component-1","name":"Diagnostic"}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID",
        ),
        (
            '[{"uid":"component-1","name":"Diagnostic","approval_mode":"unknown"}]',
            "DATTO_COMPONENT_EXECUTION_APPROVAL_MODE_INVALID",
        ),
        (
            '[{"uid":"*","name":"Diagnostic","approval_mode":"standing_safe"}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID",
        ),
        (
            '[{"uid":"component-1","name":"Diagnostic","approval_mode":"standing_safe","extra":true}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID",
        ),
        (
            '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"},'
            '{"uid":"component-1","name":"Diagnostic Two","approval_mode":"per_run"}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_AMBIGUOUS",
        ),
        (
            '[{"uid":"component-1","name":"Diagnostic","approval_mode":"standing_safe"},'
            '{"uid":"component-2","name":"diagnostic","approval_mode":"per_run"}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_AMBIGUOUS",
        ),
    ],
)
def test_invalid_scope_fails_closed(monkeypatch, payload, reason):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(DATTO_EXECUTION_COMPONENTS_JSON_ENV, payload)

    with pytest.raises(DattoComponentScopeError) as exc:
        configured_datto_components()

    assert str(exc.value) == reason


def test_crossed_uid_name_pair_fails_closed(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"},'
        '{"uid":"component-2","name":"Diagnostic Two","approval_mode":"per_run"}]',
    )

    components = configured_datto_components()

    with pytest.raises(DattoComponentScopeError) as exc:
        resolve_datto_component(
            components,
            component_uid="component-1",
            component_name="Diagnostic Two",
        )

    assert str(exc.value) == "DATTO_COMPONENT_IDENTITY_MISMATCH"
''',
    )


def patch_runtime_tests() -> None:
    path = "implementation/runtime_service/tests/test_datto_component_execution_runtime.py"
    replace_once(
        path,
        """        '[{"uid":"component-uid-1","name":"Pilot Diagnostic"},'
        '{"uid":"component-uid-2","name":"Secondary Diagnostic"}]',
""",
        """        '[{"uid":"component-uid-1","name":"Pilot Diagnostic","approval_mode":"standing_safe"},'
        '{"uid":"component-uid-2","name":"Secondary Diagnostic","approval_mode":"per_run"}]',
""",
    )
    replace_once(
        path,
        """    assert [item.uid for item in pilot.components] == [
        "component-uid-1",
        "component-uid-2",
    ]
""",
        """    assert [item.uid for item in pilot.components] == [
        "component-uid-1",
        "component-uid-2",
    ]
    assert pilot.components[0].requires_explicit_approval is False
    assert pilot.components[1].requires_explicit_approval is True
""",
    )


def patch_existing_mcp_tests() -> None:
    path = "implementation/mcp_service/tests/test_generic_governed_execution_contract.py"

    replace_once(
        path,
        """    def governed_execute(*, capability_name, arguments):
        captured["capability"] = capability_name
        captured["arguments"] = arguments
        return {"status": "succeeded"}
""",
        """    def governed_execute(
        *,
        capability_name,
        arguments,
        explicit_approval=False,
    ):
        captured["capability"] = capability_name
        captured["arguments"] = arguments
        captured["explicit_approval"] = explicit_approval
        return {"status": "succeeded"}
""",
    )

    replace_once(
        path,
        '    assert captured["capability"] == "service.ticket.note.create"\n',
        '    assert captured["capability"] == "service.ticket.note.create"\n'
        '    assert captured["explicit_approval"] is False\n',
    )

    replace_once(
        path,
        """        '[{"uid":"component-456","name":"Get-DNS Settings AOT Ver 06042025-1"},'
        '{"uid":"component-789","name":"Check Datto EDR/AV Status AOT Ver 12122025-1"}]',
""",
        """        '[{"uid":"component-456","name":"Get-DNS Settings AOT Ver 06042025-1","approval_mode":"standing_safe"},'
        '{"uid":"component-789","name":"Check Datto EDR/AV Status AOT Ver 12122025-1","approval_mode":"standing_safe"},'
        '{"uid":"component-reboot","name":"Scheduled Reboot AOT Ver 12112025-1","approval_mode":"per_run"}]',
""",
    )


def write_mcp_policy_tests() -> None:
    path = "implementation/mcp_service/tests/test_datto_component_approval_policy.py"
    write(
        path,
        '''from types import SimpleNamespace

from jason_mcp import server


def set_scope(monkeypatch):
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
            "device_uid": "device-123",
            "component_uid": "component-reboot",
        },
    )

    assert result["status"] == "approval_required"
    assert "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED" in result["reason_codes"]
    assert approvals == []
    assert calls == []


def test_per_run_proceeds_with_current_explicit_approval(monkeypatch):
    set_scope(monkeypatch)
    approvals, calls = install_runtime(monkeypatch)

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "device-123",
            "component_uid": "component-reboot",
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
''',
    )


def main() -> int:
    if already_applied():
        print("DATTO_APPROVAL_POLICY_MIGRATION=ALREADY_APPLIED")
    else:
        patch_scope()
        patch_runtime()
        patch_mcp_server()
        write_scope_tests()
        patch_runtime_tests()
        patch_existing_mcp_tests()
        write_mcp_policy_tests()
        print("DATTO_APPROVAL_POLICY_MIGRATION=APPLIED")

    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "implementation/runtime_service/src/jason_runtime/datto_component_scope.py",
            "implementation/runtime_service/src/jason_runtime/datto_component_execution.py",
            "implementation/mcp_service/src/jason_mcp/server.py",
            "implementation/mcp_service/tests/test_datto_component_approval_policy.py",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "implementation/runtime_service/tests/test_datto_component_scope.py",
            "implementation/runtime_service/tests/test_datto_component_execution_runtime.py",
            "implementation/mcp_service/tests/test_generic_governed_execution_contract.py",
            "implementation/mcp_service/tests/test_datto_component_approval_policy.py",
        ]
    )

    print("DATTO_APPROVAL_POLICY_TESTS=PASS")
    print("PROVIDER_ACCESS=NO")
    print("PROVIDER_WRITE=NO")
    print("DEPLOYMENT_CHANGE=NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"DATTO_APPROVAL_POLICY_MIGRATION=FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
