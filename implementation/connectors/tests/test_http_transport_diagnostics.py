from __future__ import annotations

import json

from connectors.core.http_transport import (
    _bounded_text,
    _provider_error_fields,
    _redact_diagnostic_text,
)


def test_provider_error_fields_extract_nested_error_object() -> None:
    raw = json.dumps(
        {
            "error": {
                "type": "insufficient_quota",
                "code": "credit_balance_exhausted",
                "param": "model",
                "message": "No credits remain.",
            }
        }
    ).encode("utf-8")

    fields = _provider_error_fields(raw)

    assert fields == {
        "provider_error_type": "insufficient_quota",
        "provider_error_code": "credit_balance_exhausted",
        "provider_error_param": "model",
        "provider_error_message": "No credits remain.",
    }


def test_provider_error_fields_extract_top_level_generic_error_shape() -> None:
    raw = json.dumps(
        {
            "error_type": "authorization_failed",
            "error_code": "forbidden",
            "parameter": "scope",
            "detail": "Caller is not authorized.",
        }
    ).encode("utf-8")

    fields = _provider_error_fields(raw)

    assert fields == {
        "provider_error_type": "authorization_failed",
        "provider_error_code": "forbidden",
        "provider_error_param": "scope",
        "provider_error_message": "Caller is not authorized.",
    }


def test_non_json_provider_error_body_is_not_retained() -> None:
    fields = _provider_error_fields(
        b"<html><body>upstream proxy failed</body></html>"
    )

    assert fields == {
        "provider_error_type": None,
        "provider_error_code": None,
        "provider_error_param": None,
        "provider_error_message": None,
    }


def test_nested_or_collection_fields_are_not_promoted_to_diagnostics() -> None:
    raw = json.dumps(
        {
            "error": {
                "type": {"unexpected": "object"},
                "code": ["unexpected", "list"],
                "param": None,
                "message": "Safe scalar message",
            }
        }
    ).encode("utf-8")

    fields = _provider_error_fields(raw)

    assert fields["provider_error_type"] is None
    assert fields["provider_error_code"] is None
    assert fields["provider_error_param"] is None
    assert fields["provider_error_message"] == "Safe scalar message"


def test_provider_diagnostic_text_is_bounded() -> None:
    value = "x" * 800

    bounded = _bounded_text(value)

    assert bounded is not None
    assert len(bounded) == 503
    assert bounded.endswith("...")


def test_redaction_removes_bearer_tokens() -> None:
    value = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz"

    redacted = _redact_diagnostic_text(value)

    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_removes_openai_style_keys() -> None:
    value = "provider rejected api key sk-supersecretkey123456"

    redacted = _redact_diagnostic_text(value)

    assert "sk-supersecretkey123456" not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_removes_named_secret_values() -> None:
    samples = (
        "api_key=abc123456789",
        "access_token: abc123456789",
        "refresh-token=abc123456789",
        "client secret: abc123456789",
        "secret_id=abc123456789",
        "password: abc123456789",
    )

    for value in samples:
        redacted = _redact_diagnostic_text(value)
        assert "abc123456789" not in redacted
        assert "[REDACTED]" in redacted
