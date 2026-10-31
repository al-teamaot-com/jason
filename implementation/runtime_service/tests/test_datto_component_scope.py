import pytest

from jason_runtime.datto_component_scope import (
    DATTO_EXECUTION_ALLOW_UNCLASSIFIED_PER_RUN_ENV,
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
        DATTO_EXECUTION_ALLOW_UNCLASSIFIED_PER_RUN_ENV,
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


def test_unclassified_component_requires_both_identity_fields_and_is_always_per_run(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"}]',
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_ALLOW_UNCLASSIFIED_PER_RUN_ENV,
        "true",
    )

    components = configured_datto_components()

    selected = resolve_datto_component(
        components,
        component_uid="live-component-99",
        component_name="Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024",
    )

    assert selected.uid == "live-component-99"
    assert selected.approval_mode == "per_run"
    assert selected.requires_explicit_approval is True

    with pytest.raises(DattoComponentScopeError):
        resolve_datto_component(
            components,
            component_name="Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024",
        )


def test_unclassified_fallback_cannot_override_configured_identity(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"standing_safe"}]',
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_ALLOW_UNCLASSIFIED_PER_RUN_ENV,
        "true",
    )

    components = configured_datto_components()

    with pytest.raises(DattoComponentScopeError) as exc:
        resolve_datto_component(
            components,
            component_uid="different-uid",
            component_name="Diagnostic One",
        )

    assert str(exc.value) == "DATTO_COMPONENT_IDENTITY_MISMATCH"


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


def test_durable_registry_can_promote_and_revoke_component(monkeypatch, tmp_path):
    from jason_runtime.datto_component_approval_registry import (
        DATTO_COMPONENT_APPROVAL_REGISTRY_PATH_ENV,
        approve_component,
        revoke_component,
    )

    clear_component_env(monkeypatch)
    path = tmp_path / "approvals.json"
    monkeypatch.setenv(
        DATTO_COMPONENT_APPROVAL_REGISTRY_PATH_ENV,
        str(path),
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-1","name":"Diagnostic One","approval_mode":"per_run"}]',
    )

    approve_component(
        uid="component-1",
        name="Diagnostic One",
        approved_by="person-al",
        metadata_fingerprint="b" * 64,
        path=path,
    )
    promoted = configured_datto_components()[0]
    assert promoted.approval_mode == "standing_safe"
    assert promoted.approval_source == "durable_registry"
    assert promoted.metadata_fingerprint == "b" * 64

    revoke_component(
        uid="component-1",
        name="Diagnostic One",
        revoked_by="person-al",
        path=path,
    )
    downgraded = configured_datto_components()[0]
    assert downgraded.approval_mode == "per_run"
    assert downgraded.approval_source == "durable_registry_revocation"



@pytest.mark.parametrize(
    "uid,name",
    [
        ("479d1a75-8f98-42b7-b6fb-408242bcc17e", "Change Hostname [WIN]"),
        ("f39412b2-bfdc-4ac6-b4be-f2fa8bc5f967", "Datto Endpoint Backup Agent v2 [WIN]"),
        ("9c30dab8-b76c-417d-a264-b3ca91995179",
         "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024"),
    ],
)
def test_owner_2174_approved_actions_remain_per_run_under_standing_config(
    monkeypatch, uid, name
):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        __import__("json").dumps(
            [{"uid": uid, "name": name, "approval_mode": "standing_safe"}]
        ),
    )
    observed = configured_datto_components()
    selected = resolve_datto_component(
        observed, component_uid=uid, component_name=name,
    )
    assert selected.approval_mode == "per_run"
    assert selected.requires_explicit_approval is True


@pytest.mark.parametrize(
    "uid,name",
    [
        ("479d1a75-8f98-42b7-b6fb-408242bcc17e", "Change Hostname [WIN]"),
        ("f39412b2-bfdc-4ac6-b4be-f2fa8bc5f967", "Datto Endpoint Backup Agent v2 [WIN]"),
        ("9c30dab8-b76c-417d-a264-b3ca91995179",
         "Datto EDR Force Reinstall and Upgrade [WIN] AOT 09162024"),
    ],
)
def test_owner_2174_action_classification_fails_open_to_no_one(
    monkeypatch, uid, name
):
    from jason_runtime.datto_component_scope import DattoComponentScopeError
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        __import__("json").dumps(
            [{"uid": uid, "name": name, "approval_mode": "standing_safe"}]
        ),
    )
    configured = configured_datto_components()
    with pytest.raises(DattoComponentScopeError):
        resolve_datto_component(
            configured, component_uid="unrelated-uid", component_name=name,
        )
    with pytest.raises(DattoComponentScopeError):
        resolve_datto_component(
            configured, component_uid=uid, component_name="Unrelated Action",
        )
