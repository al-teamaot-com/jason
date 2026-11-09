from connectors.constant_contact.import_preflight import preflight


def row(email="hello@example.com", consent="explicit", evidence="2026-11-09 opt-in form receipt"):
    return {"email": email, "marketing_consent": consent, "consent_evidence": evidence, "first_name": "Test"}


def test_valid_preview_fails_closed_until_suppression_inventory_verified():
    p = preflight([row()])
    assert len(p.accepted) == 1
    assert not p.executable
    assert not preflight([row()], suppression_inventory_complete=True).executable


def test_missing_consent_and_evidence_rejected():
    p = preflight([row(consent=""), row("other@example.com", evidence="")])
    assert not p.accepted
    assert {x["reason"] for x in p.rejected} == {
        "explicit_marketing_consent_not_documented", "consent_evidence_missing",
    }


def test_duplicate_and_suppressed_addresses_never_import():
    p = preflight([row("HELLO@example.com"), row("hello@example.com"), row("blocked@example.com")],
                  known_suppressed=["blocked@example.com"], suppression_inventory_complete=True)
    assert [x["reason"] for x in p.rejected] == ["duplicate_in_file", "provider_suppressed"]
    assert not p.executable


def test_changes_to_preview_change_digest():
    assert preflight([row()]).digest != preflight([row("different@example.com")]).digest


def test_invalid_email_and_oversize_field_rejected():
    p = preflight([row("invalid"), dict(row("ok@example.com"), first_name="x" * 51)])
    assert {x["reason"] for x in p.rejected} == {"invalid_email", "field_too_long"}


def test_consent_evidence_is_bound_to_preview_digest():
    a = preflight([row(evidence="first receipt")]).digest
    b = preflight([row(evidence="second receipt")]).digest
    assert a != b
