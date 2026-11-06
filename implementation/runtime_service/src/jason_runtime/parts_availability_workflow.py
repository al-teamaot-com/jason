"""Reuse Jason's governed Autotask read to open a verified parts request.

No new transport, Teams approval mechanism or Autotask provider write. Product
and warehouse IDs are durable Autotask IDs, not free-form names. The caller
must already possess the trusted signed Teams principal and ticket readback.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime
from typing import Any

from orchestrator.provider_read_capability_catalog import SERVICE_INVENTORY_ITEM_SEARCH
from .parts_inventory_lifecycle import (
    PartsScope,SQLitePartsLifecycleLedger,InventoryEvidence,PartsPlan,
    PartsLifecycleError,from_governed_autotask_inventory,plan_parts,
)


@dataclass
class GovernedPartsAvailabilityWorkflow:
    """Small reusable business operation over the existing provider-read port."""
    provider_reads: Any
    ledger: SQLitePartsLifecycleLedger

    def check(self, *, scope:PartsScope, principal:Any, signed_identity:Any,
              correlation_id:str,now:datetime)->tuple[PartsPlan,InventoryEvidence]:
        scope.validate()
        if (principal is None or principal.principal_id != scope.requester_identity_id
                or principal.organization_id!='aot'):
            raise PermissionError('parts requester must match authenticated AOT Teams principal')
        response=self.provider_reads(
            principal=principal,evidence=signed_identity,
            capability=SERVICE_INVENTORY_ITEM_SEARCH,
            arguments={'product_id':scope.product_id,
                       'inventory_location_id':scope.inventory_location_id},
            correlation_id=correlation_id,
        )
        proof=from_governed_autotask_inventory(
            response=response,scope=scope,now=now,correlation_id=correlation_id)
        plan=plan_parts(scope,proof,now=now)
        if plan.status.startswith('blocked'):
            raise PartsLifecycleError('available stock is not safely actionable')
        self.ledger.create(scope,now=now)
        self.ledger.record(request_id=scope.request_id,
            event_id='parts-inventory-'+sha256((scope.request_id+':'+correlation_id).encode()).hexdigest(),
            event_type='stock_checked',evidence_id=proof.source_evidence_id,
            provider_resource_id=proof.inventory_item_id,
            payload={'source':'autotask.inventory.items.read',
                     'scope_sha256':scope.fingerprint,
                     'source_sha256':proof.source_sha256,
                     'quantity_available':proof.available(now=now),
                     'quantity_candidate':plan.stock_candidate_quantity},
            at=now)
        return plan,proof
