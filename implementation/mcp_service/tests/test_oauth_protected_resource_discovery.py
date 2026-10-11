"""Regression: discovery must expose RFC 9728 protected-resource metadata."""
import ast
from pathlib import Path

SOURCE = Path(__file__).parents[1] / "src" / "jason_mcp" / "server.py"


def test_protected_resource_metadata_handler_and_route_exist():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {item.name for item in tree.body if isinstance(item, ast.AsyncFunctionDef)}
    assert "oauth_protected_resource_metadata" in names
    matches = [
        call for item in ast.walk(tree)
        if isinstance(item, ast.Call)
        for call in [item]
        if isinstance(call.func, ast.Attribute)
        and call.func.attr == "add_route"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "/.well-known/oauth-protected-resource"
    ]
    assert len(matches) == 1
    assert isinstance(matches[0].args[1], ast.Name)
    assert matches[0].args[1].id == "oauth_protected_resource_metadata"


def test_discovery_declares_authorization_and_resource_scopes():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    handler = next(item for item in tree.body if isinstance(item, ast.AsyncFunctionDef)
                   and item.name == "oauth_protected_resource_metadata")
    references = {n.id for n in ast.walk(handler) if isinstance(n, ast.Name)}
    assert {"JASON_RESOURCE_URL", "JASON_OAUTH_ISSUER_URL", "JASON_OAUTH_REQUEST_SCOPE"} <= references
    literal_fields = {k.value for n in ast.walk(handler) if isinstance(n, ast.Dict)
                      for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert {"resource", "authorization_servers", "scopes_supported", "bearer_methods_supported"} <= literal_fields


def test_authorization_server_discovery_resource_path_alias():
    """Resource-path probes must return canonical issuer metadata, not 404."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    routes = [
        item for item in ast.walk(tree)
        if isinstance(item, ast.Call)
        and isinstance(item.func, ast.Attribute)
        and item.func.attr == "add_route"
        and item.args
        and isinstance(item.args[0], ast.Constant)
        and item.args[0].value in {
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-authorization-server/mcp",
        }
    ]
    assert len(routes) == 2
    assert all(isinstance(call.args[1], ast.Name) and
               call.args[1].id == "oauth_authorization_server_metadata"
               for call in routes)
