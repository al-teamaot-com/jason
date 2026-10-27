"""Production regression: provider reads reuse the authenticated runtime binding.

No provider request, credential material, user account or production state.
"""
from __future__ import annotations

import ast
import inspect

from jason_runtime import composition
from jason_runtime import provider_reads


def test_provider_read_factory_receives_authenticated_runtime_binding_object():
    source = inspect.getsource(composition.build_runtime_application)
    parsed = ast.parse(source)
    callers = [
        call for call in ast.walk(parsed)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "build_provider_read_invoker"
    ]
    assert len(callers) == 1
    binding_values = [
        k.value for k in callers[0].keywords if k.arg == "bindings"
    ]
    assert len(binding_values) == 1
    assert isinstance(binding_values[0], ast.Name)
    assert binding_values[0].id == "source_authorization_bindings"


def test_provider_read_invoker_does_not_rebuild_binding_when_provided():
    source = inspect.getsource(provider_reads.build_provider_read_invoker)
    assert "bindings if bindings is not None" in source or (
        "bindings\n" in source and "if bindings is not None" in source
    )
    assert "else runtime_source_authorization_bindings_from_env" in source
    assert "bindings=effective_bindings" in source


def test_graph_enrichment_remains_fail_closed_on_unknown_directory_status(tmp_path):
    """The minimal wiring fix does not bypass Microsoft Graph/provider ACLs."""
    from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
    from orchestrator.teams_identity_binding_sqlite import (
        DirectoryEnrichedMicrosoftIdentityBindingResolver,
        SQLiteMicrosoftIdentityBindingStore,
    )

    class MissingDirectoryEvidence:
        def resolve_email(self, *, microsoft_tenant_id, microsoft_object_id):
            return None

    store = SQLiteMicrosoftIdentityBindingStore(tmp_path / "bindings.sqlite3")
    store.put(MicrosoftIdentityBinding(
        microsoft_tenant_id="tenant-aot",
        microsoft_object_id="user-opaque",
        jason_identity_id="person-entra-" + "a" * 32,
        client_id=None,
        status="active",
    ))
    resolver = DirectoryEnrichedMicrosoftIdentityBindingResolver(
        bindings=store, directory=MissingDirectoryEvidence(),
    )
    assert resolver.find_active_by_jason_identity(
        jason_identity_id="person-entra-" + "a" * 32
    ) is None
    store.close()


def test_no_new_provider_write_or_jason_managed_bypass_in_fix():
    source = inspect.getsource(composition.build_runtime_application)
    run = source[source.index("provider_read_invoker = build_provider_read_invoker("):]
    call = run[:run.index("quickbooks_read_invoker =")]
    assert "bindings=source_authorization_bindings" in call
    assert "execute_governed_capability" not in call
    assert "AUTOTASK_REQUESTER_AUTH_MODE" not in call
