from datetime import datetime,timezone
import json
import pytest
from jason_runtime.parts_inventory_lifecycle import (
    PartsScope,PartsLifecycleError,from_governed_autotask_inventory,plan_parts,
)
from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
from orchestrator.provider_read_capability_catalog import (
    SERVICE_INVENTORY_ITEM_SEARCH,AUTOTASK_CAPABILITIES,
)
from connectors.autotask.capability_manifest import build_autotask_manifest
from connectors.autotask.operations import resolve_operation_request,APPROVED_AUTOTASK_ENTITIES

NOW=datetime(2026,10,25,17,0,tzinfo=timezone.utc)
SCOPE=PartsScope('parts-a','person-tech1',456,'T20261025.0001',123,789,7,3,'AOT - room 1')


def test_provider_read_is_existing_governed_catalog_and_manifest():
    assert SERVICE_INVENTORY_ITEM_SEARCH in AUTOTASK_CAPABILITIES
    manifest=build_autotask_manifest()
    assert any(resource.resource_type=='service_inventory_item'
               and any(op.capability_name==SERVICE_INVENTORY_ITEM_SEARCH for op in resource.operations)
               for resource in manifest.resources)
    assert 'InventoryItems' in APPROVED_AUTOTASK_ENTITIES


def test_inventory_read_compiles_only_exact_product_and_location():
    adapted=adapt_autotask_arguments(SERVICE_INVENTORY_ITEM_SEARCH,
          {'product_id':789,'inventory_location_id':7})
    assert adapted['entity']=='InventoryItems'
    search=json.loads(adapted['search'])
    assert search['MaxRecords']==2
    assert search['filter']==[
        {'field':'productID','op':'eq','value':789},
        {'field':'inventoryLocationID','op':'eq','value':7},
    ]
    method,path,params,body=resolve_operation_request('autotask.entity.query',adapted)
    assert method=='GET' and path=='/V1.0/InventoryItems/query'
    assert body is None and params['search']==adapted['search']


@pytest.mark.parametrize('arguments',[
    {},{'product_id':789},{'inventory_location_id':7},
    {'product_id':-1,'inventory_location_id':7},
    {'product_id':True,'inventory_location_id':7},
    {'product_id':'789','inventory_location_id':7},
    {'product_id':789,'inventory_location_id':7,'page_size':500},
    {'product_id':789,'inventory_location_id':7,'filters':{'quantityOnHand':'999'}},
    {'product_id':789,'inventory_location_id':7,'search':'{"malicious":true}'},
])
def test_inventory_read_unreviewed_scope_fails_before_provider_request(arguments):
    with pytest.raises(ValueError,match='inventory query requires'):
        adapt_autotask_arguments(SERVICE_INVENTORY_ITEM_SEARCH,arguments)


def provider_response(*,rows=None):
    return {'provider':'autotask','provider_capability':'autotask.entity.query',
      'data':{'items':rows if rows is not None else [{
        'id':557,'productID':789,'inventoryLocationID':7,
        'quantityOnHand':5,'quantityPicked':1,'quantityReserved':1,
      }]}}


def test_governed_autotask_response_normalizes_authoritative_stock():
    evidence=from_governed_autotask_inventory(
        response=provider_response(),scope=SCOPE,now=NOW,correlation_id='autotask-read-1')
    assert evidence.inventory_item_id==557
    assert evidence.available(now=NOW)==3
    plan=plan_parts(SCOPE,evidence,now=NOW)
    assert plan.stock_candidate_quantity==3
    assert plan.status=='pending_provider_stock_reservation'


def test_response_rejects_missing_source_multiple_rows_and_location_mismatch():
    item=provider_response()['data']['items'][0]
    for response in (
        {'data':{'items':[item]}},
        provider_response(rows=[]),
        provider_response(rows=[item,item]),
        provider_response(rows=[dict(item,inventoryLocationID=17)]),
        provider_response(rows=[dict(item,quantityReserved=None)]),
    ):
        with pytest.raises(PartsLifecycleError):
            from_governed_autotask_inventory(
                response=response,scope=SCOPE,now=NOW,correlation_id='autotask-read-2')


def test_serialized_inventory_requires_distinct_serial_evidence():
    from dataclasses import replace
    serial=replace(SCOPE,serial_required=True)
    plan=plan_parts(serial,None,now=NOW)
    assert plan.status=='blocked_serial_inventory_confirmation_required'
    assert plan.stock_candidate_quantity==0
