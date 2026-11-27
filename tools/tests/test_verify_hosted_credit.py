from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def load_module():
    path = Path(__file__).resolve().parents[2] / 'implementation/runtime_service/src/jason_runtime/verify_hosted_credit.py'
    spec = importlib.util.spec_from_file_location('verify_hosted_credit', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_retired_diagnostic_denies_even_with_legacy_paid_config(monkeypatch, capsys):
    mod = load_module()
    monkeypatch.setenv("JASON_OPENAI_CONVERSATION_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("JASON_HOSTED_CONVERSATION_ENABLED", "true")
    monkeypatch.setenv("JASON_OPENAI_API_FALLBACK_ENABLED", "true")
    assert mod.run() == 2
    assert "PAID_AI_API_PROHIBITED" in capsys.readouterr().out
    assert not hasattr(mod, "OpenBaoSecretResolver")
    assert not hasattr(mod, "OpenAIStructuredJsonClient")


def test_metered_receipt_rejects_other_request_and_unmetered(tmp_path):
    import json
    import sqlite3
    mod = load_module()
    path = tmp_path / 'ledger.sqlite3'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE model_usage_entries (payload_json TEXT)')
    base = {'provider':'openai','outcome':'completed','usage_source':'provider_reported',
        'tokens':{'total_tokens':3},'context':{'request_id':'wrong',
        'workflow_id':'provider-credit-verify','routing_profile':'operator-authorized-diagnostic'}}
    db.execute('INSERT INTO model_usage_entries VALUES (?)', (json.dumps(base),))
    db.commit()
    assert mod.metered_receipt(path, 'correct') is False
    base['context']['request_id'] = 'correct'
    base['tokens']['total_tokens'] = 0
    db.execute('INSERT INTO model_usage_entries VALUES (?)', (json.dumps(base),))
    db.commit()
    assert mod.metered_receipt(path, 'correct') is False
    base['tokens']['total_tokens'] = 9
    db.execute('INSERT INTO model_usage_entries VALUES (?)', (json.dumps(base),))
    db.commit()
    assert mod.metered_receipt(path, 'correct') is True
    db.close()
