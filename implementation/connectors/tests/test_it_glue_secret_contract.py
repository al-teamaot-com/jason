from connectors.core.openbao_secrets import (
    DEFAULT_FIELDS,
    DEFAULT_MAPPINGS,
)


def test_it_glue_logical_secret_maps_to_approved_path() -> None:
    assert DEFAULT_MAPPINGS["it_glue.readonly"] == (
        "secret/data/connectors/it-glue/"
        "production/read-only"
    )


def test_it_glue_secret_contract_allows_only_required_fields() -> None:
    assert DEFAULT_FIELDS["it_glue.readonly"] == frozenset(
        {
            "api_key",
        }
    )


def test_it_glue_and_autotask_use_separate_secret_paths() -> None:
    assert (
        DEFAULT_MAPPINGS["it_glue.readonly"]
        != DEFAULT_MAPPINGS["autotask.readonly"]
    )


def test_it_glue_base_url_is_provider_configuration() -> None:
    from connectors.it_glue.connector import ItGlueConnector

    assert ItGlueConnector.base_url == "https://api.itglue.com"
    assert "base_url" not in DEFAULT_FIELDS["it_glue.readonly"]


def test_write_logical_alias_is_explicit_and_absent_from_default_read_resolver():
    import pytest
    from pathlib import Path
    from connectors.core.openbao_secrets import (
        IT_GLUE_WRITE_SHARED_MAPPINGS, IT_GLUE_WRITE_SHARED_FIELDS,
        OpenBaoSecretResolver, OpenBaoSecretResolutionError,
    )
    from connectors.core.contracts import ConnectorContext
    assert "it_glue.readwrite" not in DEFAULT_MAPPINGS
    assert "it_glue.readwrite" not in DEFAULT_FIELDS
    assert IT_GLUE_WRITE_SHARED_MAPPINGS == {
        "it_glue.readwrite": DEFAULT_MAPPINGS["it_glue.readonly"]}
    assert IT_GLUE_WRITE_SHARED_FIELDS == {"it_glue.readwrite": frozenset({"api_key"})}
    # Denial precedes opening even a local AppRole file or making network calls.
    def unexpected(*args, **kwargs): raise AssertionError("secret access was attempted")
    kwargs=dict(base_url="http://unused.invalid", role_id_path=Path("/nonexistent"),
                secret_id_path=Path("/nonexistent"), opener=unexpected)
    context=ConnectorContext(correlation_id="test",principal_id="test",
        organization_id="aot",client_id=None,capability="test",mode="observe")
    default=OpenBaoSecretResolver(**kwargs)
    with pytest.raises(OpenBaoSecretResolutionError,match="not configured"):
        default.resolve("it_glue.readwrite",context)
    writer=OpenBaoSecretResolver(**kwargs,mappings=IT_GLUE_WRITE_SHARED_MAPPINGS,
        allowed_fields=IT_GLUE_WRITE_SHARED_FIELDS)
    with pytest.raises(OpenBaoSecretResolutionError,match="not configured"):
        writer.resolve("it_glue.readonly",context)
