"""Operator-authorized, one-shot hosted credit diagnostic.

Run inside the existing Jason runtime with its existing OpenBao binding.
Never accept a credential or untrusted provider URL as a command argument.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from connectors.core.contracts import ConnectorContext
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from orchestrator.openai_reasoning import OpenAIStructuredJsonClient
from usage_ledger.contracts import UsageContext
from usage_ledger.ledger import SQLiteUsageLedger
from usage_ledger.runtime_context import bind_usage_context


def run() -> int:
    model = os.getenv('JASON_OPENAI_CONVERSATION_MODEL', '').strip()
    if not model:
        print('BLOCKED: configured conversation model not provided')
        return 2
    receipt = str(uuid4())
    resolver = OpenBaoSecretResolver(
        base_url=os.getenv('JASON_OPENBAO_URL', 'http://openbao:8200'),
        role_id_path=Path(os.getenv('JASON_OPENAI_OPENBAO_ROLE_ID_PATH', '/run/jason-secrets/openbao/openai/role_id')),
        secret_id_path=Path(os.getenv('JASON_OPENAI_OPENBAO_SECRET_ID_PATH', '/run/jason-secrets/openbao/openai/secret_id')),
    )
    try:
        secrets = dict(resolver.resolve('openai.semantic_intent', ConnectorContext(
            correlation_id=receipt, principal_id='jason-runtime', organization_id='aot',
            client_id=None, capability='conversation.reason', mode='observe')))
        try:
            key = secrets['api_key']
            ledger = SQLiteUsageLedger(Path(os.getenv('JASON_MODEL_USAGE_DB', '/var/lib/jason/openclaw/model-usage.sqlite3')))
            client = OpenAIStructuredJsonClient(
                api_key=key, transport=UrlLibJsonHttpTransport(), model=model,
                usage_ledger=ledger, reasoning_effort='minimal', timeout_seconds=30.0,
            )
            context = UsageContext(
                workflow_id='provider-credit-verify', request_id=receipt,
                attempt_id=str(uuid4()), organization_id='aot', client_id=None,
                capability='conversation.reason', agent_name='jason-runtime',
                routing_profile='operator-authorized-diagnostic',
                metadata={'purpose':'one-shot-hosted-credit-verification'},
            )
            with bind_usage_context(context):
                result = client.complete(
                    system='Return the required JSON object only.',
                    user='Return ok true.',
                    schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False},
                    max_output_tokens=64,
                )
            if result.get('ok') is not True:
                print('BLOCKED: diagnostic did not return expected result')
                return 3
            print(json.dumps({'result':'provider_call_completed','request_id':receipt,'model':model}))
            return 0
        finally:
            secrets.clear()
    except Exception as error:
        print('BLOCKED: diagnostic failed (' + type(error).__name__ + ')')
        return 4


if __name__ == '__main__':
    sys.exit(run())
