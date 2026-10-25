from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_module():
    path = Path(__file__).resolve().parents[1] / 'verify_hosted_credit.py'
    spec = importlib.util.spec_from_file_location('verify_hosted_credit', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_model_denies_without_provider(monkeypatch, capsys):
    mod = load_module()
    monkeypatch.delenv('JASON_OPENAI_CONVERSATION_MODEL', raising=False)
    assert mod.run() == 2
    assert 'configured conversation model' in capsys.readouterr().out


def test_diagnostic_calls_existing_ledger_with_attribution(monkeypatch, capsys):
    mod = load_module()
    monkeypatch.setenv('JASON_OPENAI_CONVERSATION_MODEL', 'gpt-5.4-mini')
    observed = {}
    class Resolver:
        def __init__(self, **kwargs):
            observed['secret_paths'] = (str(kwargs['role_id_path']), str(kwargs['secret_id_path']))
        def resolve(self, name, context):
            assert name == 'openai.semantic_intent'
            assert context.mode == 'observe'
            return {'api_key': 'test-only'}
    class Client:
        def __init__(self, **kwargs):
            observed['client'] = kwargs
        def complete(self, **kwargs):
            from usage_ledger.runtime_context import new_attempt_context
            observed['context'] = new_attempt_context()
            return {'ok': True}
    monkeypatch.setattr(mod, 'OpenBaoSecretResolver', Resolver)
    monkeypatch.setattr(mod, 'OpenAIStructuredJsonClient', Client)
    monkeypatch.setattr(mod, 'SQLiteUsageLedger', lambda path: SimpleNamespace(path=path))
    assert mod.run() == 0
    assert observed['context'].workflow_id == 'provider-credit-verify'
    assert observed['context'].routing_profile == 'operator-authorized-diagnostic'
    assert observed['client']['model'] == 'gpt-5.4-mini'
    assert observed['client']['api_key'] == 'test-only'
    assert 'test-only' not in capsys.readouterr().out


def test_error_does_not_leak_secret(monkeypatch, capsys):
    mod = load_module()
    monkeypatch.setenv('JASON_OPENAI_CONVERSATION_MODEL', 'gpt-5.4-mini')
    class Resolver:
        def __init__(self, **kwargs): pass
        def resolve(self, *args): raise RuntimeError('sensitive-private-token')
    monkeypatch.setattr(mod, 'OpenBaoSecretResolver', Resolver)
    assert mod.run() == 4
    output = capsys.readouterr().out
    assert 'RuntimeError' in output
    assert 'sensitive-private-token' not in output
