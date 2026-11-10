import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "src/jason_mcp/release_owner_identity.py"
spec = importlib.util.spec_from_file_location("release_owner_identity", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _decision(**changes):
    data = dict(
        principal=module.LICENSED_OWNER_PRINCIPAL,
        organization_id="aot",
        assurance="entra-oauth-bearer",
        verified_token_claims={
            "tid": module.OWNER_TENANT_ID,
            "oid": module.LICENSED_OWNER_OID,
            "preferred_username": "al@teamaot.com",
        },
        existing_owner_identities=frozenset({"person-al"}),
    )
    data.update(changes)
    return module.authorized_release_owner(**data)


def test_licensed_regular_owner_oauth_authorized_only_for_release():
    assert _decision() is True


def test_other_accounts_and_chat_text_cannot_authorize_release():
    for changes in (
        {"principal": "person-anyone"},
        {"principal": "person-entra-c848022de13b445784b0e2f5c00dcaf6"},
        {"assurance": "chat_text"},
        {"assurance": "unsigned_header"},
        {"organization_id": "different"},
        {"verified_token_claims": None},
        {"verified_token_claims": {"tid": module.OWNER_TENANT_ID}},
        {"verified_token_claims": {
            "tid": module.OWNER_TENANT_ID,
            "oid": "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
        }},
        {"verified_token_claims": {
            "tid": "00000000-0000-0000-0000-000000000000",
            "oid": module.LICENSED_OWNER_OID,
        }},
    ):
        assert _decision(**changes) is False, changes


def test_owner_allowlist_is_not_expanded_to_every_aot_account():
    assert _decision(
        principal="person-entra-00000000000000000000000000000000",
        verified_token_claims={
            "tid": module.OWNER_TENANT_ID,
            "oid": "00000000-0000-0000-0000-000000000000",
        },
        existing_owner_identities=frozenset({"person-al"}),
    ) is False


def test_prior_person_al_binding_retains_existing_owner_role():
    assert _decision(
        principal="person-al",
        verified_token_claims={
            "tid": module.OWNER_TENANT_ID,
            "oid": "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
        },
    ) is True


def test_server_uses_release_only_policy_without_changing_global_admin_owner():
    server = (ROOT / "src/jason_mcp/server.py").read_text()
    begin = server.index("def _release_approval_owner()")
    end = server.index("\n\n@mcp.tool()", begin)
    release = server[begin:end]
    assert "authorized_release_owner" in release
    assert "get_access_token()" in release
    assert 'raise PermissionError("RELEASE_APPROVAL_OWNER_REQUIRED")' in release
    admin_begin = server.index("def _authority_admin_owner()")
    admin_end = server.index("\n\n", admin_begin)
    assert "authorized_release_owner" not in server[admin_begin:admin_end]
