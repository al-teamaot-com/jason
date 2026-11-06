from datetime import datetime,timezone
from types import SimpleNamespace
import pytest

from jason_runtime.parts_availability_workflow import GovernedPartsAvailabilityWorkflow
from jason_runtime.parts_inventory_lifecycle import (
    SQLitePartsLifecycleLedger,PartsScope,PartsLifecycleError,
)
from orchestrator.provider_read_capability_catalog import SERVICE_INVENTORY_ITEM_SEARCH

NOW=datetime(2026,10,25,17,20,tzinfo=timezone.utc)


def scope():
    return PartsScope('parts-aot-456-789','person-tech1',456,'T20261025.0001',
                      123,789,7,2,'Customer site; staging area')


def response(*,many=False):
    return {'provider':'autotask','provider_capability':'autotask.entity.query',
        'data':{'items':[
            {'id':557,'productID':789,'inventoryLocationID':7,
             'quantityOnHand':3,'quantityReserved':1,'quantityPicked':0},
        ]*(2 if many else 1)}}


def test_parts_lookup_uses_same_authorized_provider_read_and_records_stock_proof(tmp_path):
    seen=[]
    def governed_provider(**kwargs):
        seen.append(kwargs)
        return response()
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3')
    workflow=GovernedPartsAvailabilityWorkflow(governed_provider,ledger)
    principal=SimpleNamespace(principal_id='person-tech1',organization_id='aot')
    identity=SimpleNamespace(transport='signed_microsoft_teams')
    plan,proof=workflow.check(scope=scope(),principal=principal,signed_identity=identity,
                              correlation_id='provider-read-20261025-a',now=NOW)
    assert len(seen)==1
    assert seen[0]['principal'] is principal and seen[0]['evidence'] is identity
    assert seen[0]['capability']==SERVICE_INVENTORY_ITEM_SEARCH
    assert seen[0]['arguments']=={'product_id':789,'inventory_location_id':7}
    assert plan.stock_candidate_quantity==2 and plan.unfilled_quantity==0
    assert ledger.read(scope().request_id)['state']=='stock_checked'
    events=ledger.events(scope().request_id)
    assert len(events)==1 and events[0]['provider_resource_id']==557
    assert events[0]['scope_sha256']==scope().fingerprint
    assert ledger.read(scope().request_id)['provider_po_id'] is None
    # Same correlation id retry returns the same event, not a duplicate.
    workflow.check(scope=scope(),principal=principal,signed_identity=identity,
                   correlation_id='provider-read-20261025-a',now=NOW)
    assert len(ledger.events(scope().request_id))==1


def test_wrong_teams_principal_or_organization_never_queries_provider(tmp_path):
    workflow=GovernedPartsAvailabilityWorkflow(lambda **kwargs:pytest.fail('cannot query'),
        SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3'))
    for principal in (SimpleNamespace(principal_id='person-other',organization_id='aot'),
                      SimpleNamespace(principal_id='person-tech1',organization_id='client')):
        with pytest.raises(PermissionError,match='authenticated AOT Teams'):
            workflow.check(scope=scope(),principal=principal,signed_identity=object(),
                           correlation_id='x',now=NOW)
    assert workflow.ledger.read(scope().request_id) is None


def test_ambiguous_provider_result_never_registers_part_request(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3')
    workflow=GovernedPartsAvailabilityWorkflow(lambda **kwargs:response(many=True),ledger)
    with pytest.raises(PartsLifecycleError,match='exactly one'):
        workflow.check(scope=scope(),principal=SimpleNamespace(
            principal_id='person-tech1',organization_id='aot'),
            signed_identity=object(),correlation_id='x',now=NOW)
    assert ledger.read(scope().request_id) is None
