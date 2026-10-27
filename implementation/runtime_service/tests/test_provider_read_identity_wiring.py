"""Regression: source read connectors must share MCP's authenticated binding resolver."""
import ast
import inspect
from jason_runtime import composition


def test_runtime_passes_authenticated_binding_resolver_to_provider_reads():
    source = inspect.getsource(composition.build_runtime_application)
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_provider_read_invoker"
    ]
    assert len(calls) == 1
    binding_args = [
        kw.value for kw in calls[0].keywords if kw.arg == "bindings"
    ]
    assert len(binding_args) == 1
    assert isinstance(binding_args[0], ast.Name)
    assert binding_args[0].id == "source_authorization_bindings"
