from orchestrator.investigation_redaction import (
    redact_model_evidence,
)


def test_redacts_sensitive_keys_recursively():
    result = redact_model_evidence(
        {
            "hostname": "NODE-1",
            "nested": {
                "client_secret": "secret-value",
            },
        }
    )

    assert result["hostname"] == "NODE-1"
    assert (
        result["nested"]["client_secret"]
        == "[REDACTED]"
    )


def test_redacts_generic_sensitive_name_value_record():
    result = redact_model_evidence(
        {
            "variables": [
                {
                    "name": "backup api token",
                    "value": "secret-value",
                },
                {
                    "name": "location",
                    "value": "Richmond",
                },
            ]
        }
    )

    assert (
        result["variables"][0]["value"]
        == "[REDACTED]"
    )

    assert (
        result["variables"][1]["value"]
        == "Richmond"
    )
