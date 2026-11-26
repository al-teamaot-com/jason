"""Retired paid-AI credit diagnostic; historical receipts remain readable.

Owner prohibits separately metered AI/API tokens. This entrypoint cannot
resolve a credential, contact a model provider, or spend credits.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def metered_receipt(ledger_path: Path, request_id: str) -> bool:
    """Require a real, same-request provider-reported metered completion."""
    db = sqlite3.connect(ledger_path.as_uri() + '?mode=ro', uri=True, timeout=2)
    try:
        rows = db.execute('SELECT payload_json FROM model_usage_entries ORDER BY rowid DESC LIMIT 256').fetchall()
    finally:
        db.close()
    for (raw,) in rows:
        entry = json.loads(raw)
        context = entry.get('context') or {}
        tokens = entry.get('tokens') or {}
        if (context.get('request_id') == request_id
                and context.get('workflow_id') == 'provider-credit-verify'
                and context.get('routing_profile') == 'operator-authorized-diagnostic'
                and entry.get('provider') == 'openai'
                and entry.get('outcome') == 'completed'
                and entry.get('usage_source') == 'provider_reported'
                and int(tokens.get('total_tokens') or 0) > 0):
            return True
    return False



def run() -> int:
    print("BLOCKED: PAID_AI_API_PROHIBITED; use approved non-metered engineering route")
    return 2


if __name__ == "__main__":
    sys.exit(run())
