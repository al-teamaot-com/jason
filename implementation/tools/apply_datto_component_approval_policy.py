#!/usr/bin/env python3
"""Apply and validate Jason's server-controlled Datto component approval policy.

This is a deterministic source migration. It performs no provider calls, does
not modify credentials/grants, and does not deploy or restart services.

Policy introduced by this migration:
- standing_safe: exact server-classified non-disruptive diagnostic component;
  Jason may satisfy the existing approval-required authority grant with a
  short-lived server policy approval record, so no separate per-run human
  approval is required.
- per_run: exact server-classified disruptive/state-changing component; a
  current explicit_approval=True signal is required before Jason creates the
  per-execution approval record and reaches the Central Orchestrator.
- unknown component identity or unknown approval mode: fail closed.

The caller cannot supply or override approval_mode. It is read only from the
server's exact component configuration.
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
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise MigrationError(
            f"{path}: expected exactly one source match, found {count}"
        )
    write(path, content.replace(old, new, 1))


def insert_before_once(path: str, marker: str, addition: str) -> None:
    content = read(path)
    count = content.count(marker)
    if count != 1:
        raise MigrationError(
            f"{path}: expected exactly one insertion marker, found {count}"
        )
    write(path, content.replace(marker, addition + marker, 1))


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
        'DATTO_EXECUTION_COMPONENT_NAME_ENV = (\n    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME"\n)\n\n_MAX_COMPONENTS = 16\n',
        'DATTO_EXECUTION_COMPONENT_NAME_ENV = (\n    "JASON_DATTO_COMPONENT_EXECUTION_COMPONENT_NAME"\n)\n\nDATTO_APPROVAL_MODE_STANDING_SAFE = "standing_safe"\nDATTO_APPROVAL_MODE_PER_RUN = "per_run"\n_VALID_APPROVAL_MODES = frozenset(\n    {\n        DATTO_APPROVAL_MODE_STANDING_SAFE,\n        DATTO_APPROVAL_MODE_PER_RUN,\n    }\n)\n\n_MAX_COMPONENTS = 16\n',
    )

    replace_once(
        path,
        '@dataclass(frozen=True, slots=True)\nclass DattoApprovedComponent:\n    uid: str\n    name: str\n',
        '@dataclass(frozen=True, slots=True)\nclass DattoApprovedComponent:\n    uid: str\n    name: str\n    approval_mode: str = DATTO_APPROVAL_MODE_PER_RUN\n\n    @property\n    def requires_explicit_approval(self) -> bool:\n        return self.approval_mode == DATTO_APPROVAL_MODE_PER_RUN\n',
    )

    replace_once(
        path,
        'def _normalize_component(uid: object, name: object) -> DattoApprovedComponent:\n    normalized_uid = str(uid or "").strip()\n    normalized_name = str(name or "").strip()\n',
        'def _normalize_component(\n    uid: object,\n    name: object,\n    approval_mode: object = DATTO_APPROVAL_MODE_PER_RUN,\n) -> DattoApprovedComponent:\n    normalized_uid = str(uid or "").strip()\n    normalized_name = str(name or "").strip()\n    normalized_approval_mode = str(approval_mode or "").strip().casefold()\n',
    )

    replace_once(
        path,
        '    if (\n        normalized_uid.casefold() in _FORBIDDEN_SCOPE_VALUES\n        or normalized_name.casefold() in _FORBIDDEN_SCOPE_VALUES\n    ):\n        raise DattoComponentScopeError(\n            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"\n        )\n\n    return DattoApprovedComponent(\n        uid=normalized_uid,\n        name=normalized_name,\n    )\n',
        '    if (\n        normalized_uid.casefold() in _FORBIDDEN_SCOPE_VALUES\n        or normalized_name.casefold() in _FORBIDDEN_SCOPE_VALUES\n    ):\n        raise DattoComponentScopeError(\n            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"\n        )\n\n    if normalized_approval_mode not in _VALID_APPROVAL_MODES:\n        raise DattoComponentScopeError(\n            "DATTO_COMPONENT_EXECUTION_APPROVAL_MODE_INVALID"\n        )\n\n    return DattoApprovedComponent(\n        uid=normalized_uid,\n        name=normalized_name,\n        approval_mode=normalized_approval_mode,\n    )\n',
    )

    replace_once(
        path,
        '            if set(item) != {"uid", "name"}:\n',
        '            if set(item) != {"uid", "name", "approval_mode"}:\n',
    )

    replace_once(
        path,
        '                _normalize_component(\n                    item.get("uid"),\n                    item.get("name"),\n                )\n',
        '                _normalize_component(\n                    item.get("uid"),\n                    item.get("name"),\n                    item.get("approval_mode"),\n                )\n',
    )


def patch_runtime() -> None:
    path = "implementation/runtime_service/src/jason_runtime/datto_component_execution.py"

    replace_once(
        path,
        '            "conversation_authenticated_imperative_is_approval": (\n                "true"\n            ),\n            "pilot_scope": "aot_owner_exact_component_exact_endpoint",\n',
        '            "conversation_authenticated_imperative_is_approval": (\n                "false"\n            ),\n            "component_approval_policy": (\n                "server_classified_standing_safe_or_per_run"\n            ),\n            "pilot_scope": "aot_owner_exact_component_exact_endpoint",\n',
    )

    replace_once(
        path,
        '                    requires_per_run_approval=True,\n',
        '                    requires_per_run_approval=(\n                        selected_component.requires_explicit_approval\n                    ),\n',
    )


def patch_mcp_server() -> None:
    path = "implementation/mcp_service/src/jason_mcp/server.py"

    replace_once(
        path,
        'def _governed_execute(\n    *,\n    capability_name: str,\n    arguments: Mapping[str, Any],\n) -> dict[str, Any]:\n',
        'def _governed_execute(\n    *,\n    capability_name: str,\n    arguments: Mapping[str, Any],\n    explicit_approval: bool = False,\n) -> dict[str, Any]:\n',
    )

    replace_once(
        path,
        '    execution_id = f"exec_mcp_action_{uuid4().hex}"\n    correlation_id = f"corr_mcp_action_{uuid4().hex}"\n',
        '    datto_approval_mode: str | None = None\n\n    if capability_name == "automation.component.execute":\n        try:\n            selected_component = resolve_datto_component(\n                configured_datto_components(),\n                component_uid=canonical_arguments.get("component_uid"),\n                component_name=canonical_arguments.get("component_name"),\n            )\n        except ValueError as exc:\n            return {\n                "status": "rejected",\n                "capability": capability_name,\n                "error_code": "invalid_action_arguments",\n                "reason_codes": [str(exc)],\n            }\n\n        datto_approval_mode = selected_component.approval_mode\n\n    execution_id = f"exec_mcp_action_{uuid4().hex}"\n    correlation_id = f"corr_mcp_action_{uuid4().hex}"\n',
    )

    old_approval = '''    if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:\n        imperative_approval = (\n            str(\n                metadata.get(\n                    "conversation_authenticated_imperative_is_approval",\n                    "",\n                )\n            ).casefold()\n            == "true"\n        )\n\n        if not imperative_approval:\n            return {\n                "status": "approval_required",\n                "capability": capability_name,\n                "reason_codes": list(decision.reason_codes),\n                "correlation_id": correlation_id,\n            }\n\n        approval_repository = getattr(\n'''

    new_approval = '''    if decision.outcome is AuthorityOutcome.APPROVAL_REQUIRED:\n        approval_decided_by = principal\n\n        if capability_name == "automation.component.execute":\n            if datto_approval_mode == "standing_safe":\n                imperative_approval = True\n                approval_decided_by = "policy:datto-standing-safe"\n            elif datto_approval_mode == "per_run":\n                imperative_approval = explicit_approval is True\n\n                if not imperative_approval:\n                    return {\n                        "status": "approval_required",\n                        "capability": capability_name,\n                        "reason_codes": [\n                            "DATTO_COMPONENT_EXPLICIT_APPROVAL_REQUIRED",\n                            *list(decision.reason_codes),\n                        ],\n                        "correlation_id": correlation_id,\n                    }\n            else:\n                return {\n                    "status": "denied",\n                    "capability": capability_name,\n                    "reason_codes": [\n                        "DATTO_COMPONENT_APPROVAL_MODE_INVALID",\n                    ],\n                    "correlation_id": correlation_id,\n                }\n        else:\n            imperative_approval = (\n                str(\n                    metadata.get(\n                        "conversation_authenticated_imperative_is_approval",\n                        "",\n                    )\n                ).casefold()\n                == "true"\n            )\n\n        if not imperative_approval:\n            return {\n                "status": "approval_required",\n                "capability": capability_name,\n                "reason_codes": list(decision.reason_codes),\n                "correlation_id": correlation_id,\n            }\n\n        approval_repository = getattr(\n'''
    replace_once(path, old_approval, new_approval)

    replace_once(
        path,
        '                decided_by=principal,\n',
        '                decided_by=approval_decided_by,\n',
    )

    replace_once(
        path,
        '        "write_authority": (\n            "jason_exact_grant_plus_per_execution_approval"\n            if write_enabled\n            else None\n        ),\n',
        '        "write_authority": (\n            "jason_exact_grant_plus_server_governed_approval_policy"\n            if write_enabled\n            else None\n        ),\n        "datto_component_approval_policy": (\n            "server_classified_standing_safe_or_per_run"\n            if "automation.component.execute" in actions\n            else None\n        ),\n',
    )

    replace_once(
        path,
        'def execute_governed_capability(\n    capability: str,\n    arguments: dict[str, Any],\n) -> dict[str, Any]:\n',
        'def execute_governed_capability(\n    capability: str,\n    arguments: dict[str, Any],\n    explicit_approval: bool = False,\n) -> dict[str, Any]:\n',
    )

    replace_once(
        path,
        '    Microsoft Entra authenticates the caller; Jason authority, approval policy,\n    Central Orchestrator routing, provider isolation, attempt limits and audit\n    remain authoritative.\n',
        '    Microsoft Entra authenticates the caller; Jason authority, approval policy,\n    Central Orchestrator routing, provider isolation, attempt limits and audit\n    remain authoritative. For server-classified Datto per_run components,\n    explicit_approval must be true only after the authenticated technician has\n    explicitly approved that exact execution. standing_safe classification is\n    server-controlled and never accepted from action arguments.\n',
    )

    replace_once(
        path,
        '    return _governed_execute(\n        capability_name=capability_name,\n        arguments=dict(arguments or {}),\n    )\n',
        '    return _governed_execute(\n        capability_name=capability_name,\n        arguments=dict(arguments or {}),\n        explicit_approval=(explicit_approval is True),\n    )\n',
    )


def patch_scope_tests() -> None:
    path = "implementation/runtime_service/tests/test_datto_component_scope.py"

    replace_once(
        path,
        '    assert components[0].name == "Diagnostic One"\n',
        '    assert components[0].name == "Diagnostic One"\n    assert components[0].approval_mode == "per_run"\n    assert components[0].requires_explicit_approval is True\n',
    )

    replacements = {
        '[{"uid":"component-1","name":"Diagnostic One"},': '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"},',
        '{"uid":"component-2","name":"Diagnostic Two"}]': '{"uid":"component-2","name":"Diagnostic Two","approval_mode":"per_run"}]',
        '[{"uid":"*","name":"Diagnostic"}]': '[{"uid":"*","name":"Diagnostic","approval_mode":"standing_safe"}]',
        '[{"uid":"component-1","name":"Diagnostic","extra":true}]': '[{"uid":"component-1","name":"Diagnostic","approval_mode":"standing_safe","extra":true}]',
        '[{"uid":"component-1","name":"Diagnostic One"},\'\n            \'{"uid":"component-1","name":"Diagnostic Two"}]': '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"},\'\n            \'{"uid":"component-1","name":"Diagnostic Two","approval_mode":"per_run"}]',
        '[{"uid":"component-1","name":"Diagnostic"},\'\n            \'{"uid":"component-2","name":"diagnostic"}]': '[{"uid":"component-1","name":"Diagnostic","approval_mode":"standing_safe"},\'\n            \'{"uid":"component-2","name":"diagnostic","approval_mode":"per_run"}]',
    }

    content = read(path)
    for old, new in replacements.items():
        content = content.replace(old, new)
    write(path, content)

    insert_before_once(
        path,
        '        (\n            \'[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"},\'\n',
        '        (\n            \'[{"uid":"component-1","name":"Diagnostic"}]\',\n            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID",\n        ),\n        (\n            \'[{"uid":"component-1","name":"Diagnostic","approval_mode":"unknown"}]\',\n            "DATTO_COMPONENT_EXECUTION_APPROVAL_MODE_INVALID",\n        ),\n',
    )

    replace_once(
        path,
        '    assert resolve_datto_component(\n        components,\n        component_uid="component-2",\n        component_name="Diagnostic Two",\n    ).uid == "component-2"\n',
        '    selected = resolve_datto_component(\n        components,\n        component_uid="component-2",\n        component_name="Diagnostic Two",\n    )\n    assert selected.uid == "component-2"\n    assert selected.approval_mode == "per_run"\n    assert selected.requires_explicit_approval is True\n    assert components[0].approval_mode == "standing_safe"\n    assert components[0].requires_explicit_approval is False\n',
    )


def patch_runtime_tests() -> None:
    path = "implementation/runtime_service/tests/test_datto_component_execution_runtime.py"

    replace_once(
        path,
        '        \'[{"uid":"component-uid-1","name":"Pilot Diagnostic"},\'\n        \'{"uid":"component-uid-2","name":"Secondary Diagnostic"}]\',\n',
        '        \'[{"uid":"component-uid-1","name":"Pilot Diagnostic","approval_mode":"standing_safe"},\'\n        \'{"uid":"component-uid-2","name":"Secondary Diagnostic","approval_mode":"per_run"}]\',\n',
    )

    replace_once(
        path,
        '    assert [item.uid for item in pilot.components] == [\n        "component-uid-1",\n        "component-uid-2",\n    ]\n',
        '    assert [item.uid for item in pilot.components] == [\n        "component-uid-1",\n        "component-uid-2",\n    ]\n    assert pilot.components[0].requires_explicit_approval is False\n    assert pilot.components[1].requires_explicit_approval is True\n',
    )

    replace_once(
        path,
        '                DattoApprovedComponent(\n                    uid="component-uid-1",\n                    name="Pilot Diagnostic",\n                ),\n                DattoApprovedComponent(\n                    uid="component-uid-2",\n                    name="Secondary Diagnostic",\n                ),\n',
        '                DattoApprovedComponent(\n                    uid="component-uid-1",\n                    name="Pilot Diagnostic",\n                    approval_mode="standing_safe",\n                ),\n                DattoApprovedComponent(\n                    uid="component-uid-2",\n                    name="Secondary Diagnostic",\n                    approval_mode="per_run",\n                ),\n',
    )


def patch_mcp_tests() -> None:
    path = "implementation/mcp_service/tests/test_generic_governed_execution_contract.py"

    replace_once(
        path,
        '    def governed_execute(*, capability_name, arguments):\n        captured["capability"] = capability_name\n        captured["arguments"] = arguments\n        return {"status": "succeeded"}\n',
        '    def governed_execute(\n        *,\n        capability_name,\n        arguments,\n        explicit_approval=False,\n    ):\n        captured["capability"] = capability_name\n        captured["arguments"] = arguments\n        captured["explicit_approval"] = explicit_approval\n        return {"status": "succeeded"}\n',
    )

    replace_once(
        path,
        '    assert captured["capability"] == "service.ticket.note.create"\n',
        '    assert captured["capability"] == "service.ticket.note.create"\n    assert captured["explicit_approval"] is False\n',
    )

    replace_once(
        path,
        '        \'[{"uid":"component-456","name":"Get-DNS Settings AOT Ver 06042025-1"},\'\n        \'{"uid":"component-789","name":"Check Datto EDR/AV Status AOT Ver 12122025-1"}]\',\n',
        '        \'[{"uid":"component-456","name":"Get-DNS Settings AOT Ver 06042025-1","approval_mode":"standing_safe"},\'\n        \'{"uid":"component-789","name":"Check Datto EDR/AV Status AOT Ver 12122025-1","approval_mode":"standing_safe"},\'\n        \'{"uid":"component-reboot","name":"Scheduled Reboot AOT Ver 12112025-1","approval_mode":"per_run"}]\',\n',
    )

    addition = r'''

def _install_governed_datto_test_runtime(monkeypatch):
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


def test_datto_standing_safe_component_needs_no_explicit_per_run_approval(
    monkeypatch,
):
    _set_datto_multi_component_scope(monkeypatch)
    approvals, orchestrator_calls = _install_governed_datto_test_runtime(
        monkeypatch
    )

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "device-123",
            "component_uid": "component-456",
        },
    )

    assert result["status"] == "succeeded"
    assert len(orchestrator_calls) == 1
    assert len(approvals) == 1
    assert approvals[0].decided_by == "policy:datto-standing-safe"


def test_datto_per_run_component_fails_before_orchestrator_without_explicit_approval(
    monkeypatch,
):
    _set_datto_multi_component_scope(monkeypatch)
    approvals, orchestrator_calls = _install_governed_datto_test_runtime(
        monkeypatch
    )

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
    assert orchestrator_calls == []


def test_datto_per_run_component_proceeds_only_with_explicit_approval(
    monkeypatch,
):
    _set_datto_multi_component_scope(monkeypatch)
    approvals, orchestrator_calls = _install_governed_datto_test_runtime(
        monkeypatch
    )

    result = server._governed_execute(
        capability_name="automation.component.execute",
        arguments={
            "device_uid": "device-123",
            "component_uid": "component-reboot",
        },
        explicit_approval=True,
    )

    assert result["status"] == "succeeded"
    assert len(orchestrator_calls) == 1
    assert len(approvals) == 1
    assert approvals[0].decided_by == "person-al"


def test_datto_caller_cannot_override_server_approval_mode(monkeypatch):
    _set_datto_multi_component_scope(monkeypatch)

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
'''

    content = read(path)
    marker = "\ndef test_datto_action_rejects_different_target(monkeypatch):\n"
    if marker not in content:
        raise MigrationError(f"{path}: Datto test insertion marker missing")
    content = content.replace(marker, addition + marker, 1)
    write(path, content)


def main() -> int:
    if already_applied():
        print("DATTO_APPROVAL_POLICY_MIGRATION=ALREADY_APPLIED")
    else:
        patch_scope()
        patch_runtime()
        patch_mcp_server()
        patch_scope_tests()
        patch_runtime_tests()
        patch_mcp_tests()
        print("DATTO_APPROVAL_POLICY_MIGRATION=APPLIED")

    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "implementation/runtime_service/src/jason_runtime/datto_component_scope.py",
            "implementation/runtime_service/src/jason_runtime/datto_component_execution.py",
            "implementation/mcp_service/src/jason_mcp/server.py",
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
