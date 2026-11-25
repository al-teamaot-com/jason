from dataclasses import replace
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jason_runtime.constant_contact_import_runtime import (
    ConstantContactBindingError, RequesterBoundImportInvoker,
    read_protected_account_binding,
)
from orchestrator.contracts import OrchestrationMode


def bound_request(**overrides):
    base = dict(
        capability_name="marketing.contact.import",
        principal_id="aot-owner", organization_id="aot", client_id=None,
        authority_allowed=True, authority_context_id="trusted-current-context",
        approval_present=True, approval_id="planstep-trusted-approved",
        requester_kind="human", permission_mode="execute",
        orchestration_mode=OrchestrationMode.EXECUTE,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def resolution():
    return SimpleNamespace(
        capability_name="marketing.contact.import",
        selected_provider_id="constant_contact",
    )


def test_auth_gate_does_not_invoke_connector_for_invalid_principal():
    delegate = Mock()
    bindings = Mock()
    bindings.find_active_by_jason_identity.return_value = None
    invoker = RequesterBoundImportInvoker(delegate, bindings)
    with pytest.raises(PermissionError, match="not authorized"):
        invoker.prepare_execution_plan(
            request=bound_request(), resolution=resolution(),
        )
    delegate.prepare_execution_plan.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"organization_id": "external"},
    {"client_id": "unapproved-client"},
    {"permission_mode": "observe"},
    {"approval_id": None},
    {"approval_present": False},
    {"authority_context_id": None},
    {"requester_kind": "service"},
])
def test_invalid_import_scope_rejected_before_provider(overrides):
    delegate = Mock()
    bindings = Mock()
    bindings.find_active_by_jason_identity.return_value = object()
    invoker = RequesterBoundImportInvoker(delegate, bindings)
    with pytest.raises(PermissionError, match="not authorized"):
        invoker.prepare_execution_plan(
            request=bound_request(**overrides), resolution=resolution(),
        )
    delegate.prepare_execution_plan.assert_not_called()


def test_bound_request_delegates_only_to_governed_plan_invoker():
    delegate = Mock()
    bindings = Mock()
    bindings.find_active_by_jason_identity.return_value = object()
    invoker = RequesterBoundImportInvoker(delegate, bindings)
    invoker.prepare_execution_plan(
        request=bound_request(), resolution=resolution(),
    )
    delegate.prepare_execution_plan.assert_called_once()
    with pytest.raises(PermissionError, match="prepared execution"):
        invoker.invoke(request=bound_request(), resolution=resolution())
    delegate.invoke.assert_not_called()


def test_protected_account_binding_is_exact_and_not_environment_fallback(tmp_path):
    path = tmp_path / "approved-account.json"
    path.write_text(json.dumps({
        "organization_id": "aot",
        "encoded_account_id": "aot1234567890",
        "verification_basis": "owner_approved_oauth_readback",
    }))
    path.chmod(0o640)
    assert read_protected_account_binding(
        path, required_uid=os.getuid(),
    ) == "aot1234567890"
    path.chmod(0o666)
    with pytest.raises(ConstantContactBindingError):
        read_protected_account_binding(path, required_uid=os.getuid())
    path.chmod(0o640)
    with pytest.raises(ConstantContactBindingError):
        read_protected_account_binding(path, required_uid=999999)
    alias = tmp_path / "symlink"
    alias.symlink_to(path)
    with pytest.raises(ConstantContactBindingError):
        read_protected_account_binding(alias, required_uid=os.getuid())
