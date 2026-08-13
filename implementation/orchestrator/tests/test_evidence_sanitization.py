from __future__ import annotations

from orchestrator.evidence_sanitization import (
    REDACTED,
    is_sensitive_value,
    sanitize_evidence_tree,
)


def test_sensitive_keys_are_redacted_recursively():
    source = {
        "hostname": "AOT-50282",
        "nested": {
            "password": "ordinary-looking-password",
            "apiKey": "ordinary-looking-key",
            "client_secret": "ordinary-looking-secret",
        },
    }

    sanitized = sanitize_evidence_tree(source)

    assert sanitized["hostname"] == "AOT-50282"
    assert sanitized["nested"]["password"] == REDACTED
    assert sanitized["nested"]["apiKey"] == REDACTED
    assert sanitized["nested"]["client_secret"] == REDACTED


def test_jwt_is_redacted_even_under_generic_field_name():
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikphc29uIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )

    sanitized = sanitize_evidence_tree({"value": jwt})

    assert sanitized["value"] == REDACTED


def test_private_key_is_redacted_even_under_generic_field_name():
    value = (
        "-----BEGIN PRIVATE KEY-----\n"
        "example-private-key-material\n"
        "-----END PRIVATE KEY-----"
    )

    assert sanitize_evidence_tree({"value": value})["value"] == REDACTED


def test_bearer_token_is_redacted():
    assert (
        sanitize_evidence_tree({"header": "Bearer abc.def.ghi"})["header"]
        == REDACTED
    )


def test_connection_string_secret_assignment_is_redacted():
    value = (
        "Server=db.example.test;"
        "User Id=jason;"
        "Password=super-secret-value;"
        "Database=operations"
    )

    assert sanitize_evidence_tree({"connection": value})["connection"] == REDACTED


def test_credential_uri_is_redacted():
    assert (
        sanitize_evidence_tree(
            {"endpoint": "https://username:password@example.test/resource"}
        )["endpoint"]
        == REDACTED
    )


def test_long_opaque_token_is_redacted_under_generic_field_name():
    value = "AbCDefghijklmnopQRstuvwxyz0123456789_-ABCDEFGHIJKLMNOP"

    assert len(value) >= 48
    assert is_sensitive_value(value)
    assert sanitize_evidence_tree({"value": value})["value"] == REDACTED


def test_common_operational_values_are_preserved():
    source = {
        "hostname": "AOT-50282",
        "intIpAddress": "192.168.12.33",
        "extIpAddress": "216.54.107.150",
        "lastLoggedInUser": r"AzureAD\AlDavis",
        "operatingSystem": "Microsoft Windows 11 Pro 10.0.26200",
        "device_uid": "11111111-2222-3333-4444-555555555555",
        "content_hash": "a" * 64,
    }

    sanitized = sanitize_evidence_tree(source)

    assert sanitized == source


def test_original_structure_is_not_modified():
    source = {
        "siteVariables": [
            {"name": "IntegrationPassword", "value": "top-secret"},
            {"name": "Description", "value": "normal operational text"},
        ]
    }

    sanitized = sanitize_evidence_tree(source)

    assert source["siteVariables"][0]["value"] == "top-secret"
    assert sanitized is not source


def test_secret_value_shape_catches_generic_site_variable_value():
    source = {
        "siteVariables": [
            {
                "name": "SomeIntegrationValue",
                "value": (
                    "eyJhbGciOiJIUzI1NiJ9."
                    "eyJzdWIiOiJqYXNvbiJ9."
                    "abcdefghijklmnopqrstuvwx"
                ),
            }
        ]
    }

    sanitized = sanitize_evidence_tree(source)

    assert sanitized["siteVariables"][0]["name"] == "SomeIntegrationValue"
    assert sanitized["siteVariables"][0]["value"] == REDACTED


def test_sensitive_variable_name_redacts_ordinary_sibling_value():
    source = {
        "variables": [
            {
                "name": "IntegrationPassword",
                "value": "short-ordinary-value",
            },
            {
                "name": "Description",
                "value": "normal operational text",
            },
        ]
    }

    sanitized = sanitize_evidence_tree(source)

    assert sanitized["variables"][0]["name"] == "IntegrationPassword"
    assert sanitized["variables"][0]["value"] == REDACTED
    assert sanitized["variables"][1]["name"] == "Description"
    assert sanitized["variables"][1]["value"] == "normal operational text"


def test_sensitive_key_metadata_redacts_sibling_value():
    source = {
        "setting": {
            "key": "ApiToken",
            "value": "short-token-value",
        }
    }

    sanitized = sanitize_evidence_tree(source)

    assert sanitized["setting"]["key"] == "ApiToken"
    assert sanitized["setting"]["value"] == REDACTED
