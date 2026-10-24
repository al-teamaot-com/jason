import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("probe", Path(__file__).resolve().parents[1] / "check_mcp_oauth_discovery.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_good_metadata():
    assert probe.validate("https://mcp.example", {"resource": "https://mcp.example/mcp", "authorization_servers": ["https://issuer.example/"], "scopes_supported": ["read"]}, {"issuer": "https://issuer.example/", "authorization_endpoint": "https://login.example/auth", "token_endpoint": "https://login.example/token"})


def test_rejects_missing_resource():
    try:
        probe.validate("https://mcp.example", {"resource": "https://bad.example/mcp", "authorization_servers": ["https://issuer.example/"], "scopes_supported": ["read"]}, {"issuer": "https://issuer.example/", "authorization_endpoint": "https://login.example/auth", "token_endpoint": "https://login.example/token"})
    except ValueError:
        return
    raise AssertionError("bad resource must fail")


def test_rejects_issuer_disagreement():
    try:
        probe.validate("https://mcp.example", {"resource": "https://mcp.example/mcp", "authorization_servers": ["https://issuer.example/"], "scopes_supported": ["read"]}, {"issuer": "https://other.example/", "authorization_endpoint": "https://login.example/auth", "token_endpoint": "https://login.example/token"})
    except ValueError:
        return
    raise AssertionError("issuer mismatch must fail")
