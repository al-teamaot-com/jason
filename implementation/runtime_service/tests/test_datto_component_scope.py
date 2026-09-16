import pytest

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


def test_legacy_single_component_fallback(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_UID_ENV,
        "component-1",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_NAME_ENV,
        "Diagnostic One",
    )

    components = configured_datto_components()

    assert len(components) == 1
    assert components[0].uid == "component-1"
    assert components[0].name == "Diagnostic One"


def test_json_scope_is_authoritative_and_exact(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_UID_ENV,
        "legacy-component",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENT_NAME_ENV,
        "Legacy Diagnostic",
    )
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-1","name":"Diagnostic One"},'
        '{"uid":"component-2","name":"Diagnostic Two"}]',
    )

    components = configured_datto_components()

    assert [item.uid for item in components] == [
        "component-1",
        "component-2",
    ]
    assert resolve_datto_component(
        components,
        component_uid="component-2",
        component_name="Diagnostic Two",
    ).uid == "component-2"


@pytest.mark.parametrize(
    "payload,reason",
    [
        ("not-json", "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"),
        ("[]", "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID"),
        (
            '[{"uid":"*","name":"Diagnostic"}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID",
        ),
        (
            '[{"uid":"component-1","name":"Diagnostic","extra":true}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_INVALID",
        ),
        (
            '[{"uid":"component-1","name":"Diagnostic One"},'
            '{"uid":"component-1","name":"Diagnostic Two"}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_AMBIGUOUS",
        ),
        (
            '[{"uid":"component-1","name":"Diagnostic"},'
            '{"uid":"component-2","name":"diagnostic"}]',
            "DATTO_COMPONENT_EXECUTION_SERVER_SCOPE_AMBIGUOUS",
        ),
    ],
)
def test_invalid_scope_fails_closed(monkeypatch, payload, reason):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        payload,
    )

    with pytest.raises(DattoComponentScopeError) as exc:
        configured_datto_components()

    assert str(exc.value) == reason


def test_crossed_uid_name_pair_fails_closed(monkeypatch):
    clear_component_env(monkeypatch)
    monkeypatch.setenv(
        DATTO_EXECUTION_COMPONENTS_JSON_ENV,
        '[{"uid":"component-1","name":"Diagnostic One"},'
        '{"uid":"component-2","name":"Diagnostic Two"}]',
    )

    components = configured_datto_components()

    with pytest.raises(DattoComponentScopeError) as exc:
        resolve_datto_component(
            components,
            component_uid="component-1",
            component_name="Diagnostic Two",
        )

    assert str(exc.value) == "DATTO_COMPONENT_IDENTITY_MISMATCH"
