"""Offline acceptance: reuse verified Jason MCP Owner and signed shadow proof."""
from __future__ import annotations

from types import SimpleNamespace
import pytest

from kernel.signed_owner_release import OWNER_OID, OWNER_PRINCIPAL
from jason_mcp import pmv4_owner_bridge as bridge

C = "a" * 40
R = "b" * 40
S = "c" * 64
M = "d" * 64
F = "e" * 64


def arguments(**overrides):
    values = dict(
        bearer_token="verified-opaque-mcp-bearer",
        verified_owner_principal=OWNER_PRINCIPAL,
        verified_organization="aot",
        verify_entra_bearer=lambda token: {"oid": OWNER_OID},
        candidate_sha=C, rollback_sha=R, scope_sha256=S,
        manifest_sha256=M, freeze_sha256=F,
        affirmative_decision="approve_exact_pmv4_shadow_release",
    )
    values.update(overrides)
    return values


def test_binds_existing_verified_session_to_exact_host_manifest(monkeypatch):
    calls = []
    def issue(**kwargs):
        calls.append(kwargs)
        assert kwargs["production"] is True
        assert kwargs["root"] == bridge.PRODUCTION_ROOT
        assert kwargs["protected_main_check"] is bridge.public_protected_main_head
        assert kwargs["jwt_verifier"]("verified-opaque-mcp-bearer")["oid"] == OWNER_OID
        assert kwargs["exact_owner_consent"]({
            "service": "jason-pmv4-shadow", "owner_principal": OWNER_PRINCIPAL,
            "candidate_sha": C, "rollback_sha": R, "scope_sha256": S,
            "manifest_sha256": M, "freeze_sha256": F,
        })
        return {"status": "owner_decision_signed_for_exact_shadow_release"}
    monkeypatch.setattr(bridge, "issue_shadow_owner_proof", issue)
    assert bridge.authorize_exact_shadow_from_mcp(**arguments())["status"].startswith("owner_decision")
    assert len(calls) == 1
    for field in ("candidate_sha", "rollback_sha", "scope_sha256", "manifest_sha256", "freeze_sha256"):
        incorrect = {
            "service": "jason-pmv4-shadow", "owner_principal": OWNER_PRINCIPAL,
            "candidate_sha": C, "rollback_sha": R, "scope_sha256": S,
            "manifest_sha256": M, "freeze_sha256": F,
        }
        incorrect[field] = "bad"
        assert not calls[0]["exact_owner_consent"](incorrect)
    assert not calls[0]["exact_owner_consent"]({"service": "another"})


@pytest.mark.parametrize("overrides,reason", [
    ({"verified_organization": "another"}, "PMV4_MCP_VERIFIED_OWNER_REQUIRED"),
    ({"verified_owner_principal": "other"}, "PMV4_MCP_VERIFIED_OWNER_REQUIRED"),
    ({"affirmative_decision": ""}, "PMV4_MCP_EXPLICIT_EXACT_APPROVAL_REQUIRED"),
    ({"affirmative_decision": "yes"}, "PMV4_MCP_EXPLICIT_EXACT_APPROVAL_REQUIRED"),
    ({"verify_entra_bearer": None}, "PMV4_MCP_ENTRA_VERIFIER_UNAVAILABLE"),
])
def test_rejects_untrusted_session_or_non_exact_consent(overrides, reason, monkeypatch):
    monkeypatch.setattr(bridge, "issue_shadow_owner_proof", lambda **_: pytest.fail("must not issue"))
    with pytest.raises(PermissionError, match=reason):
        bridge.authorize_exact_shadow_from_mcp(**arguments(**overrides))


def test_rejects_subject_spoof_and_missing_signed_token_claims(monkeypatch):
    def issuer(**kw):
        kw["jwt_verifier"](kw["bearer_token"])
    monkeypatch.setattr(bridge, "issue_shadow_owner_proof", issuer)
    with pytest.raises(PermissionError, match="VERIFIED_SUBJECT_MISMATCH"):
        bridge.authorize_exact_shadow_from_mcp(**arguments(
            verify_entra_bearer=lambda _: {"oid": "wrong-oid"}))
    with pytest.raises(PermissionError, match="ENTRA_VERIFICATION_DENIED"):
        bridge.authorize_exact_shadow_from_mcp(**arguments(
            verify_entra_bearer=lambda _: None))


def test_decision_does_not_accept_different_bearer(monkeypatch):
    def issuer(**kw):
        kw["jwt_verifier"]("client-substituted-token")
    monkeypatch.setattr(bridge, "issue_shadow_owner_proof", issuer)
    with pytest.raises(PermissionError, match="AUTHENTICATED_TOKEN_MISMATCH"):
        bridge.authorize_exact_shadow_from_mcp(**arguments())


def test_public_protected_main_precheck_requires_exact_source(monkeypatch):
    import io
    import json
    seen = []
    class Response(io.BytesIO):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.close()
    def fake_open(request, timeout):
        seen.append((request.full_url, timeout))
        obj = {
            "name": "main", "protected": True,
            "commit": {"sha": C},
        }
        return Response(json.dumps(obj).encode())
    monkeypatch.setattr(bridge, "urlopen", fake_open)
    assert bridge.public_protected_main_head(C) is True
    assert bridge.public_protected_main_head(R) is False
    assert bridge.public_protected_main_head("../bad") is False
    assert len(seen) == 2
    assert seen[0] == (bridge.PUBLIC_MAIN_URL, 8)


@pytest.mark.parametrize("untrusted", [
    {"name": "main", "protected": False, "commit": {"sha": C}},
    {"name": "not-main", "protected": True, "commit": {"sha": C}},
    {"name": "main", "protected": True, "commit": {"sha": R}},
    {"name": "main", "protected": True, "commit": {}},
])
def test_public_head_rejects_unprotected_or_mismatched_source(monkeypatch, untrusted):
    import io
    import json
    monkeypatch.setattr(
        bridge, "urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps(untrusted).encode()),
    )
    assert bridge.public_protected_main_head(C) is False


def test_public_branch_transport_error_fails_closed(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("GitHub network temporarily unavailable")
    monkeypatch.setattr(bridge, "urlopen", unavailable)
    assert bridge.public_protected_main_head(C) is False
