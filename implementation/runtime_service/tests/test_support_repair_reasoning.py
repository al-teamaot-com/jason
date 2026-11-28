from pathlib import Path
import json

from connectors.core.contracts import ConnectorTransportError

from jason_runtime.support_repair_reasoning import (
    SupportRepairReasoningMaintenance,
    _request_id,
)


class Client:
    def __init__(self):
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if 'diagnostician' in kwargs['system']:
            return {'diagnosis': 'queue alias mismatch', 'search_terms': ['queueName', 'queueID'], 'blocked_reason': None}
        return {
            'summary': 'normalize queue alias',
            'edits': [{'path': 'implementation/example.py', 'old_text': 'queueName', 'new_text': 'queueID'}],
            'test_paths': ['implementation/tests/test_example.py'],
            'blocked_reason': None,
        }


def _request(kind):
    payload = {
        'kind': kind,
        'support_item': 'SUPPORT-OPS-999',
        'title': 'Synthetic repair',
        'evidence': 'Observed failure',
        'acceptance': 'Regression passes',
        'context': {},
    }
    payload['request_id'] = _request_id(payload)
    return payload


def test_reasoning_maintenance_processes_bounded_search_request(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('search_plan')
    (request_dir / f"{request['request_id']}.json").write_text(json.dumps(request), encoding='utf-8')

    maintenance = SupportRepairReasoningMaintenance(
        structured_client=client,
        spool=tmp_path,
        interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{request['request_id']}.json").read_text())
    assert response['status'] == 'succeeded'
    assert response['result']['search_terms'] == ['queueName', 'queueID']
    assert len(client.calls) == 1


def test_reasoning_maintenance_accepts_legacy_development_request_kind(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('development')
    (request_dir / f"{request['request_id']}.json").write_text(json.dumps(request), encoding='utf-8')

    maintenance = SupportRepairReasoningMaintenance(
        structured_client=client,
        spool=tmp_path,
        interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{request['request_id']}.json").read_text())
    assert response['status'] == 'succeeded'
    assert response['result']['summary'] == 'normalize queue alias'
    assert len(client.calls) == 1


def test_reasoning_accepts_owner_approved_development_work_item(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    payload = {
        'kind': 'search_plan',
        'support_item': 'DEV-676',
        'title': 'Owner-only staff activity audit',
        'evidence': 'Owner-approved issue scope',
        'acceptance': 'Regression passes',
        'context': {'work_class': 'owner_approved_development'},
    }
    payload['request_id'] = _request_id(payload)
    (request_dir / f"{payload['request_id']}.json").write_text(json.dumps(payload), encoding='utf-8')
    maintenance = SupportRepairReasoningMaintenance(structured_client=client, spool=tmp_path, interval_seconds=1)
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{payload['request_id']}.json").read_text())
    assert response['status'] == 'succeeded'
    assert len(client.calls) == 1
    assert 'owner-approved development diagnostician' in client.calls[0]['system']


def test_support_dev_recovery_keeps_support_repair_prompts(tmp_path: Path):
    # A recovery SUPPORT-DEV-* item is a support incident, not a newly
    # owner-approved DEV-* implementation request.  Reclassifying the former
    # silently changes prompt scope and cannot fix a transport HTTP 400.
    for kind, expected_role in (
        ('search_plan', 'support-repair diagnostician'),
        ('edit_plan', 'repair patch proposer'),
    ):
        base = tmp_path / kind
        request_dir = base / 'reasoning' / 'requests'
        request_dir.mkdir(parents=True)
        payload = _request(kind)
        payload['support_item'] = 'SUPPORT-DEV-1196'
        payload['request_id'] = _request_id(payload)
        (request_dir / f"{payload['request_id']}.json").write_text(
            json.dumps(payload), encoding='utf-8'
        )
        client = Client()
        worker = SupportRepairReasoningMaintenance(
            structured_client=client, spool=base, interval_seconds=1
        )
        assert worker.tick() is True
        assert len(client.calls) == 1
        system = client.calls[0]['system']
        assert expected_role in system
        assert 'owner-approved development' not in system
        response = json.loads((base / 'reasoning' / 'responses' /
                               f"{payload['request_id']}.json").read_text())
        assert response['status'] == 'succeeded'


def test_explicit_dev_edit_plan_retains_owner_approved_development_prompt(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    payload = _request('edit_plan')
    payload['support_item'] = 'DEV-1196'
    payload['request_id'] = _request_id(payload)
    (request_dir / f"{payload['request_id']}.json").write_text(
        json.dumps(payload), encoding='utf-8'
    )
    client = Client()
    worker = SupportRepairReasoningMaintenance(
        structured_client=client, spool=tmp_path, interval_seconds=1
    )
    assert worker.tick() is True
    assert len(client.calls) == 1
    assert 'owner-approved development patch proposer' in client.calls[0]['system']
    response = json.loads((tmp_path / 'reasoning' / 'responses' /
                           f"{payload['request_id']}.json").read_text())
    assert response['status'] == 'succeeded'


def test_reasoning_maintenance_rejects_tampered_request(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('search_plan')
    request['evidence'] = 'tampered'
    (request_dir / f"{request['request_id']}.json").write_text(json.dumps(request), encoding='utf-8')
    maintenance = SupportRepairReasoningMaintenance(structured_client=Client(), spool=tmp_path, interval_seconds=1)
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{request['request_id']}.json").read_text())
    assert response['status'] == 'failed'
    assert 'fingerprint' in response['error']


def test_completed_requests_do_not_starve_later_pending_request(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)

    # Four alphabetically earlier requests are already complete. The bounded
    # processor must select from unresolved requests rather than slicing first.
    for index in range(4):
        name = f'0{index}.json'
        (request_dir / name).write_text('{}', encoding='utf-8')
        (response_dir / name).write_text('{"status":"succeeded"}', encoding='utf-8')

    request = _request('search_plan')
    pending_path = request_dir / f"{request['request_id']}.json"
    pending_path.write_text(json.dumps(request), encoding='utf-8')

    maintenance = SupportRepairReasoningMaintenance(
        structured_client=client,
        spool=tmp_path,
        interval_seconds=1,
    )

    assert maintenance.tick() is True
    response_path = response_dir / pending_path.name
    assert response_path.exists()
    response = json.loads(response_path.read_text(encoding='utf-8'))
    assert response['status'] == 'succeeded'
    assert len(client.calls) == 1


class TransientFailureClient:
    def __init__(self, status_code=429):
        self.status_code = status_code
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        raise ConnectorTransportError(
            f"HTTP transport failed with status {self.status_code}",
            status_code=self.status_code,
        )


def test_transient_failed_response_retries_with_local_fallback(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)
    request = _request('search_plan')
    request_path = request_dir / f"{request['request_id']}.json"
    response_path = response_dir / request_path.name
    request_path.write_text(json.dumps(request), encoding='utf-8')
    response_path.write_text(
        json.dumps({
            'status': 'failed',
            'request_id': request['request_id'],
            'error_type': 'ConnectorTransportError',
            'error': 'HTTP transport failed with status 429',
        }),
        encoding='utf-8',
    )
    primary = TransientFailureClient(429)
    fallback = Client()
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=primary,
        fallback_structured_client=fallback,
        spool=tmp_path,
        interval_seconds=1,
    )

    assert maintenance.tick() is True
    response = json.loads(response_path.read_text(encoding='utf-8'))
    assert response['status'] == 'succeeded'
    assert response['result']['search_terms'] == ['queueName', 'queueID']
    assert primary.calls == 1
    assert len(fallback.calls) == 1
    assert fallback.calls[0]['max_output_tokens'] == 1024


def test_previous_ollama_budget_failure_is_bounded_retry_candidate(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)
    request = _request('search_plan')
    request_path = request_dir / f"{request['request_id']}.json"
    response_path = response_dir / request_path.name
    request_path.write_text(json.dumps(request), encoding='utf-8')
    response_path.write_text(json.dumps({
        'status': 'failed',
        'request_id': request['request_id'],
        'error_type': 'ValueError',
        'error': 'Ollama structured reasoning output budget is invalid',
        'attempts': 1,
    }), encoding='utf-8')
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=Client(),
        spool=tmp_path,
        interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads(response_path.read_text(encoding='utf-8'))
    assert response['status'] == 'succeeded'


def test_second_scope_review_separates_code_diagnosis_from_deployment(tmp_path: Path):
    client = Client()
    request = _request('search_plan')
    request['context'] = {'scope_review': 'source_diagnosis_only',
                          'prior_blocked_reason': 'root-governed rollback needs authority'}
    request['request_id'] = _request_id(request)
    root = tmp_path / 'reasoning' / 'requests'
    root.mkdir(parents=True)
    (root / (request['request_id'] + '.json')).write_text(json.dumps(request))
    maint = SupportRepairReasoningMaintenance(structured_client=client, spool=tmp_path, interval_seconds=1)
    assert maint.tick() is True
    assert len(client.calls) == 1
    prompt = client.calls[0]['system']
    assert 'source-only diagnosis' in prompt.lower()
    assert 'does not itself require production' in prompt
    assert 'Do not infer that permission' in prompt
    assert 'root-governed' in prompt


def test_hosted_patch_400_recovers_once_through_bounded_local_fallback(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    response_dir = tmp_path / 'reasoning' / 'responses'
    request_dir.mkdir(parents=True)
    response_dir.mkdir(parents=True)
    request = _request('edit_plan')
    (request_dir / (request['request_id'] + '.json')).write_text(json.dumps(request))
    (response_dir / (request['request_id'] + '.json')).write_text(json.dumps({
        'status': 'failed', 'request_id': request['request_id'],
        'error_type': 'ConnectorTransportError',
        'error': 'HTTP transport failed with status 400', 'attempts': 1,
    }))
    primary = TransientFailureClient(400)
    fallback = Client()
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=primary, fallback_structured_client=fallback,
        spool=tmp_path, interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads((response_dir / (request['request_id'] + '.json')).read_text())
    assert response['status'] == 'succeeded'
    assert response['result']['edits'][0]['path'] == 'implementation/example.py'
    assert primary.calls == 1
    assert len(fallback.calls) == 1
    assert fallback.calls[0]['max_output_tokens'] <= 1024


def test_hosted_search_400_does_not_bypass_request_validation(tmp_path: Path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('search_plan')
    (request_dir / (request['request_id'] + '.json')).write_text(json.dumps(request))
    fallback = Client()
    maintenance = SupportRepairReasoningMaintenance(
        structured_client=TransientFailureClient(400),
        fallback_structured_client=fallback, spool=tmp_path, interval_seconds=1,
    )
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / (request['request_id'] + '.json')).read_text())
    assert response['status'] == 'failed'
    assert fallback.calls == []


def test_transport_failure_spool_keeps_only_bounded_diagnostic_code(tmp_path: Path):
    class FailedClient:
        def complete(self, **kwargs):
            raise ConnectorTransportError('HTTP transport failed', provider_error_code='DNS_RESOLUTION')

    request = _request('search_plan')
    directory = tmp_path / 'reasoning' / 'requests'
    directory.mkdir(parents=True)
    (directory / f"{request['request_id']}.json").write_text(json.dumps(request))
    maintenance = SupportRepairReasoningMaintenance(structured_client=FailedClient(), spool=tmp_path)
    assert maintenance.tick() is True
    response = json.loads((tmp_path / 'reasoning' / 'responses' / f"{request['request_id']}.json").read_text())
    assert response['status'] == 'failed'
    assert response['transport_failure_code'] == 'DNS_RESOLUTION'
    assert response['attempts'] == 1


class BillingFailureClient:
    def __init__(self, code='credit_balance_exhausted'):
        self.calls=0
        self.code=code
    def complete(self, **kwargs):
        self.calls+=1
        raise ConnectorTransportError('HTTP transport failed with status 429',status_code=429,
            provider_error_type='insufficient_quota',provider_error_code=self.code)


class FailedFallbackClient:
    def __init__(self):self.calls=0
    def complete(self, **kwargs):
        self.calls+=1
        raise ConnectorTransportError('HTTP transport failed')


def test_empty_credit_error_survives_fallback_failure_and_is_not_retried(tmp_path):
    from datetime import datetime,timedelta,timezone
    clock=[datetime(2026,10,16,tzinfo=timezone.utc)]
    primary=BillingFailureClient();fallback=FailedFallbackClient()
    directory=tmp_path/'reasoning'/'requests';directory.mkdir(parents=True)
    request=_request('search_plan')
    (directory/(request['request_id']+'.json')).write_text(json.dumps(request))
    maint=SupportRepairReasoningMaintenance(structured_client=primary,fallback_structured_client=fallback,
        spool=tmp_path,interval_seconds=1,now=lambda:clock[0])
    assert maint.tick()
    response=json.loads((tmp_path/'reasoning'/'responses'/(request['request_id']+'.json')).read_text())
    assert response['status']=='failed'
    assert response['primary_provider_error_code']=='credit_balance_exhausted'
    assert response['fallback_status']=='failed'
    assert response['required_owner_action']=='restore_provider_credits'
    assert response['retryable'] is False
    assert 'credit_balance_exhausted' in response['error']
    clock[0]+=timedelta(seconds=2)
    assert maint.tick() is False
    assert primary.calls==1 and fallback.calls==1


def test_configured_fallback_can_complete_without_hiding_billing_warning(tmp_path):
    primary=BillingFailureClient();fallback=Client()
    directory=tmp_path/'reasoning'/'requests';directory.mkdir(parents=True)
    request=_request('search_plan')
    (directory/(request['request_id']+'.json')).write_text(json.dumps(request))
    maint=SupportRepairReasoningMaintenance(structured_client=primary,fallback_structured_client=fallback,spool=tmp_path)
    assert maint.tick()
    response=json.loads((tmp_path/'reasoning'/'responses'/(request['request_id']+'.json')).read_text())
    assert response['status']=='succeeded'
    assert response['primary_provider_error_code']=='credit_balance_exhausted'
    assert response['fallback_status']=='succeeded'
    assert response['required_owner_action']=='restore_provider_credits'
    assert len(fallback.calls)==1


def test_quota_failure_without_fallback_is_not_mislabeled_network_error(tmp_path):
    directory=tmp_path/'reasoning'/'requests';directory.mkdir(parents=True)
    request=_request('search_plan')
    (directory/(request['request_id']+'.json')).write_text(json.dumps(request))
    maint=SupportRepairReasoningMaintenance(structured_client=BillingFailureClient('project_spend_limit_exceeded'),spool=tmp_path)
    assert maint.tick()
    response=json.loads((tmp_path/'reasoning'/'responses'/(request['request_id']+'.json')).read_text())
    assert response['required_owner_action']=='review_project_spend_limit'
    assert response['retryable'] is False


def test_engineering_edit_schema_exposes_bounded_read_only_tool_requests():
    from jason_runtime.support_repair_reasoning import _edit_schema
    schema = _edit_schema()
    assert schema['additionalProperties'] is False
    assert 'evidence_requests' in schema['required']
    requests = schema['properties']['evidence_requests']
    assert requests['maxItems'] == 3
    props = requests['items']
    assert props['additionalProperties'] is False
    assert set(props['required']) == {'tool', 'query', 'path'}
    assert props['properties']['tool']['enum'] == ['search_source', 'read_source']


def test_engineering_edit_prompt_requests_source_evidence_instead_of_guessing(tmp_path: Path):
    client = Client()
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('edit_plan')
    path = request_dir / (request['request_id'] + '.json')
    path.write_text(json.dumps(request))
    worker = SupportRepairReasoningMaintenance(
        structured_client=client, spool=tmp_path, interval_seconds=1,
    )
    assert worker.tick() is True
    assert len(client.calls) == 1
    assert 'read-only evidence_requests' in client.calls[0]['system']
    assert 'read_source' in client.calls[0]['system']
    assert 'Do not' in client.calls[0]['system']


def test_owner_development_last_evidence_turn_requires_patch_or_genuine_blocker(tmp_path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('edit_plan')
    request['support_item'] = 'DEV-1545'
    request['context'] = {
        'work_class': 'owner_approved_development',
        'source_excerpts': [{'path': 'tools/example.py', 'content': 'def task(): pass'}],
        'evidence_turn': 4,
        'evidence_turns_remaining': 0,
        'final_evidence_turn': True,
    }
    request['request_id'] = _request_id(request)
    (request_dir / (request['request_id']+'.json')).write_text(json.dumps(request))
    client = Client()
    maint = SupportRepairReasoningMaintenance(
        structured_client=client, spool=tmp_path,
    )
    assert maint.tick()
    system = client.calls[0]['system']
    assert 'LAST authorized source-evidence turn' in system
    assert 'DO NOT return any evidence_requests' in system
    assert 'blocked_reason' in system
    assert 'Do not guess unseen text' in system


def test_normal_development_edit_turn_allows_bounded_evidence_requests(tmp_path):
    request_dir = tmp_path / 'reasoning' / 'requests'
    request_dir.mkdir(parents=True)
    request = _request('edit_plan')
    request['support_item'] = 'DEV-759'
    request['context'] = {'work_class':'owner_approved_development', 'evidence_turn':1}
    request['request_id'] = _request_id(request)
    (request_dir / (request['request_id']+'.json')).write_text(json.dumps(request))
    client=Client()
    maint=SupportRepairReasoningMaintenance(structured_client=client,spool=tmp_path)
    assert maint.tick()
    system=client.calls[0]['system']
    assert 'read-only evidence_requests' in system
    assert 'LAST authorized source-evidence turn' not in system


def test_local_primary_engineering_request_uses_extended_bounded_contract(tmp_path):
    from orchestrator.ollama_reasoning import OllamaStructuredJsonClient
    from orchestrator.model_runtime_adapter import ModelRuntimeAdapter, ollama_grammar_compatible_schema
    class Transport:
        def __init__(self): self.calls=[]
        def request(self, **kw):
            self.calls.append(kw)
            return {"message":{"content":json.dumps({
                "summary":"synthetic edit","edits":[],"test_paths":[],
                "blocked_reason":"no source in synthetic request","evidence_requests":[]})}}
    transport=Transport()
    local=ModelRuntimeAdapter(client=OllamaStructuredJsonClient(
        transport=transport,model="local-test",output_token_limit=4096,
        context_tokens=32768,timeout_seconds=180),
        schema_adapter=ollama_grammar_compatible_schema)
    req=_request("edit_plan")
    d=tmp_path/"reasoning"/"requests";d.mkdir(parents=True)
    (d/(req["request_id"]+".json")).write_text(json.dumps(req))
    maint=SupportRepairReasoningMaintenance(structured_client=local,spool=tmp_path)
    assert maint.tick()
    rsp=json.loads((tmp_path/"reasoning"/"responses"/(req["request_id"]+".json")).read_text())
    assert rsp["status"]=="succeeded" and rsp["result"]["blocked_reason"]
    assert len(transport.calls)==1
    assert transport.calls[0]["url"]=="http://jason-ollama:11434/api/chat"
    assert transport.calls[0]["json"]["options"]["num_predict"]==4096
    assert transport.calls[0]["json"]["options"]["num_ctx"]==32768

class LocalClient(Client):
    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return {"summary":"need source", "edits":[], "test_paths":[],
                "blocked_reason":None,
                "evidence_requests":[{"tool":"search_source","query":"function_name","path":None}]}


def test_bounded_local_projection_preserves_exact_original_request_and_authority(tmp_path):
    from jason_runtime.support_repair_reasoning import LOCAL_ENGINEERING_MAX_PROMPT_BYTES
    req=_request("edit_plan")
    req["support_item"]="DEV-123"
    req["context"]={
        "work_class":"owner_approved_development",
        "approval_source":"exact owner marker",
        "approved_scope":{"paths":["implementation/example.py"]},
        "pinned_source_revision":"a"*40,
        "read_only_tool_receipts":[{"tool":"read_source","path":"implementation/example.py","sha256":"b"*64}],
        "source_excerpts":[
            {"path":"implementation/example.py","content":"a=1\\n"*1000},
            {"path":"implementation/large.py","content":"# unicode é"*3000},
            {"path":"implementation/tests/test_example.py","content":"assert a==1\\n"*100},
        ],
    }
    req["request_id"]=_request_id(req)
    original=json.dumps(req,sort_keys=True)
    client=LocalClient()
    m=SupportRepairReasoningMaintenance(structured_client=client,spool=tmp_path,
        local_prompt_max_bytes=LOCAL_ENGINEERING_MAX_PROMPT_BYTES)
    m._complete(m._validate_request(req))
    assert json.dumps(req,sort_keys=True)==original
    call=client.calls[0]
    assert len(call["user"].encode("utf-8"))<=LOCAL_ENGINEERING_MAX_PROMPT_BYTES
    context=json.loads(call["user"])["context"]
    assert context["approved_scope"]==req["context"]["approved_scope"]
    assert context["approval_source"]==req["context"]["approval_source"]
    assert context["read_only_tool_receipts"]==req["context"]["read_only_tool_receipts"]
    assert context["pinned_source_revision"]==req["context"]["pinned_source_revision"]
    assert context["source_excerpts"]==[req["context"]["source_excerpts"][i] for i in (0,2)]
    assert context["local_source_projection"]["omitted_source_paths"]==["implementation/large.py"]
    assert "Never guess omitted code" in call["system"]
    assert m.attempt_diagnostics["local_source_projection"]["original_request_unchanged"]
    assert m.attempt_diagnostics["local_source_projection"]["omitted_source_count"]==1


def test_local_projection_refuses_oversized_non_source_context_before_inference(tmp_path):
    import pytest
    req=_request("edit_plan")
    req["context"]={"approved_scope":"A"*20000,
                    "source_excerpts":[{"path":"implementation/example.py","content":"a=1"}]}
    req["request_id"]=_request_id(req)
    client=LocalClient()
    m=SupportRepairReasoningMaintenance(structured_client=client,spool=tmp_path,
        local_prompt_max_bytes=16000)
    with pytest.raises(ValueError,match="bounded non-source context"):
        m._complete(m._validate_request(req))
    assert not client.calls


def test_local_budget_never_enables_fallback_or_changes_small_requests(tmp_path):
    import pytest
    client=LocalClient()
    with pytest.raises(ValueError,match="cannot use fallback"):
        SupportRepairReasoningMaintenance(structured_client=client,
            fallback_structured_client=LocalClient(),spool=tmp_path,local_prompt_max_bytes=16000)
    req=_request("edit_plan")
    m=SupportRepairReasoningMaintenance(structured_client=client,spool=tmp_path,
        local_prompt_max_bytes=16000)
    m._complete(m._validate_request(req))
    assert json.loads(client.calls[0]["user"])["context"]=={}
    assert m.attempt_diagnostics=={}

def test_local_edit_contract_denies_ambiguous_or_mixed_tool_arguments(tmp_path):
    from jason_runtime.support_repair_reasoning import _validate_local_edit_result
    import pytest
    base={"summary":"need source","edits":[],"test_paths":[],"blocked_reason":None}
    for action in (
        {"tool":"read_source","query":"implementation/example.py:func()","path":None},
        {"tool":"read_source","query":"func()","path":"implementation/example.py"},
        {"tool":"read_source","query":"func","path":"../private.py"},
        {"tool":"read_source","query":"func","path":"/etc/example.py"},
        {"tool":"search_source","query":"foo OR bar","path":None},
        {"tool":"search_source","query":"foo","path":"implementation/example.py"},
    ):
        with pytest.raises(ValueError,match="local engineering"):
            _validate_local_edit_result(dict(base,evidence_requests=[action]))
    valid={"tool":"read_source","query":"func","path":"implementation/example.py"}
    _validate_local_edit_result(dict(base,evidence_requests=[valid]))
    with pytest.raises(ValueError,match="mixed"):
        _validate_local_edit_result(dict(base,evidence_requests=[valid],blocked_reason="blocked"))
