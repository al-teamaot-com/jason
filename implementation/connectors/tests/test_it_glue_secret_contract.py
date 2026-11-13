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


def test_write_secret_does_not_alias_readonly_secret():
    assert DEFAULT_MAPPINGS["it_glue.readwrite"] == (
        "secret/data/connectors/it-glue/production/write")
    assert DEFAULT_FIELDS["it_glue.readwrite"] == frozenset({"api_key"})
    assert DEFAULT_MAPPINGS["it_glue.readwrite"] != DEFAULT_MAPPINGS["it_glue.readonly"]
