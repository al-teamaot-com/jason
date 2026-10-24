from pathlib import Path

from jason_runtime.microsoft_sharepoint import build_microsoft_sharepoint_runtime


def test_sharepoint_runtime_has_isolated_openbao_and_read_only_profile(tmp_path: Path):
    runtime = build_microsoft_sharepoint_runtime(
        boundary_db=tmp_path / "clients.sqlite",
        openbao_url="https://openbao.invalid",
        role_id_path=tmp_path / "role-id",
        secret_id_path=tmp_path / "secret-id",
        transport=object(),
    )
    tenant_tokens = runtime.reader.tokens
    assert tenant_tokens.provider_name == "microsoft_graph_sharepoint"
    assert tenant_tokens.profile_name == "sharepoint-read"
    assert tenant_tokens.tokens._logical_secret == "microsoft_graph.sharepoint_read"
    assert tenant_tokens.tokens._provider_name == "microsoft_graph_sharepoint"
    assert tenant_tokens.tokens._profile_name == "sharepoint-read"
    # Runtime composition must not perform Microsoft calls or read certificates.
    assert tenant_tokens.tokens._applications == {}
