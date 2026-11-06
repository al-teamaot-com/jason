"""Provider-neutral parts/PO/receiving evidence ledger for Jason.

Autotask is authoritative for inventory, purchase orders, ticket charges and
stock movements. This ledger records *verified provider receipts*, not imaginary
on-hand inventory or new spending authority. Every provider mutation is routed
through Jason's existing governed capability + signed purchase approval gates.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from .procurement_inventory_billing import AllocationPlan, ReleaseGate, ProcurementControlError
from .procurement_supervisor_policy import money, require_signed_purchase_approval


class PartsLifecycleError(ValueError):
    pass


_SHA=re.compile(r'[0-9a-f]{64}\Z')
_ALLOWED_EVENTS=frozenset({'stock_checked','stock_reserved','purchase_approved',
    'po_created','partial_received','received','staged','assigned','installed',
    'ticket_charged','returned','cancelled','exception'})


def digest(value: Mapping[str,Any]) -> str:
    return sha256(json.dumps(dict(value),sort_keys=True,separators=(',',':'),
                             allow_nan=False,ensure_ascii=True).encode()).hexdigest()


def require_identity(value: Any, *, name: str) -> str:
    if not isinstance(value,str) or not value.strip() or value.strip()!=value or len(value)>180:
        raise PartsLifecycleError(name+' must be a bounded canonical identity')
    return value


def require_positive_id(value: Any, *, name: str) -> int:
    if type(value) is not int or value<1:
        raise PartsLifecycleError(name+' must be an authoritative positive ID')
    return value


@dataclass(frozen=True,slots=True)
class PartsScope:
    request_id: str
    requester_identity_id: str
    ticket_id: int
    ticket_number: str
    company_id: int
    product_id: int
    inventory_location_id: int
    quantity: int
    destination: str
    serial_required: bool = False

    def validate(self)->None:
        require_identity(self.request_id,name='request')
        require_identity(self.requester_identity_id,name='requester')
        require_identity(self.ticket_number,name='ticket number')
        require_identity(self.destination,name='physical destination')
        for key in ('ticket_id','company_id','product_id','inventory_location_id','quantity'):
            require_positive_id(getattr(self,key),name=key)
        if self.quantity>1000:
            raise PartsLifecycleError('parts quantity outside reviewed bounds')
        if type(self.serial_required) is not bool:
            raise PartsLifecycleError('serial requirement must be explicit')
        # Reuse Jason's established exact ticket-linked allocation invariant.
        try:
            AllocationPlan(ordered_quantity=self.quantity,customer_quantity=self.quantity,
                aot_stock_quantity=0,ticket_id=self.ticket_id,
                ticket_number=self.ticket_number).validate()
        except ProcurementControlError as exc:
            raise PartsLifecycleError(str(exc)) from exc

    @property
    def fingerprint(self)->str:
        self.validate()
        return digest(asdict(self))


@dataclass(frozen=True,slots=True)
class InventoryEvidence:
    """Fresh Autotask InventoryItems resource readback, never user asserted."""
    inventory_item_id: int
    product_id: int
    inventory_location_id: int
    quantity_on_hand: int
    quantity_picked: int
    quantity_reserved: int
    observed_at: datetime
    source_evidence_id: str
    source_sha256: str
    provider: str = 'autotask.inventory.items.read'

    def available(self, *, now: datetime, max_age: timedelta=timedelta(minutes=10)) -> int:
        for field in ('inventory_item_id','product_id','inventory_location_id'):
            require_positive_id(getattr(self,field),name=field)
        for field in ('quantity_on_hand','quantity_picked','quantity_reserved'):
            value=getattr(self,field)
            if type(value) is not int or value<0:
                raise PartsLifecycleError('inventory quantities require authoritative nonnegative integers')
        if self.quantity_picked+self.quantity_reserved>self.quantity_on_hand:
            raise PartsLifecycleError('inventory provider counts conflict')
        if self.provider!='autotask.inventory.items.read':
            raise PartsLifecycleError('stock must come from authoritative Autotask InventoryItems')
        require_identity(self.source_evidence_id,name='inventory readback reference')
        if not isinstance(self.source_sha256,str) or not _SHA.fullmatch(self.source_sha256):
            raise PartsLifecycleError('stock readback requires SHA256 evidence')
        if (not isinstance(self.observed_at,datetime) or self.observed_at.tzinfo is None
                or not isinstance(now,datetime) or now.tzinfo is None
                or not timedelta(0)<=now-self.observed_at<=max_age):
            raise PartsLifecycleError('stale or future stock reading; requery Autotask')
        return self.quantity_on_hand-self.quantity_picked-self.quantity_reserved


@dataclass(frozen=True,slots=True)
class PartsPlan:
    request_id: str
    scope_sha256: str
    provider_snapshot_sha256: str | None
    stock_candidate_quantity: int
    unfilled_quantity: int
    status: str


def from_governed_autotask_inventory(*, response:Mapping[str,Any],
                                    scope:PartsScope,now:datetime,
                                    correlation_id:str)->InventoryEvidence:
    """Create one bounded proof from an authorized provider-read response.

    This is a normalizer, not a provider client: it must only be called with a
    result from the guarded `service.inventory.item.search` orchestration path.
    The original data/references remain in Jason's provider-read audit trail.
    """
    scope.validate()
    require_identity(correlation_id,name='read correlation id')
    if (response.get('provider')!='autotask'
            or response.get('provider_capability')!='autotask.entity.query'):
        raise PartsLifecycleError('untrusted inventory source; governed Autotask read required')
    data=response.get('data')
    if not isinstance(data,Mapping):
        raise PartsLifecycleError('Autotask inventory response lacks structured rows')
    items=data.get('items')
    if not isinstance(items,list) or len(items)!=1 or not isinstance(items[0],Mapping):
        raise PartsLifecycleError('inventory query must return exactly one product-location row')
    row=dict(items[0])
    fields=('id','productID','inventoryLocationID','quantityOnHand','quantityPicked','quantityReserved')
    if any(type(row.get(f)) is not int for f in fields):
        raise PartsLifecycleError('Autotask InventoryItems quantities/IDs are unavailable')
    proof=InventoryEvidence(
        inventory_item_id=row['id'],product_id=row['productID'],
        inventory_location_id=row['inventoryLocationID'],
        quantity_on_hand=row['quantityOnHand'],
        quantity_picked=row['quantityPicked'],quantity_reserved=row['quantityReserved'],
        observed_at=now,source_evidence_id=correlation_id,
        source_sha256=digest({'provider':'autotask','correlation_id':correlation_id,
                              'inventory_item':row}),
    )
    if (proof.product_id!=scope.product_id
            or proof.inventory_location_id!=scope.inventory_location_id):
        raise PartsLifecycleError('inventory provider row mismatched requested product/location')
    proof.available(now=now)
    return proof


def plan_parts(scope: PartsScope, stock: InventoryEvidence | None, *,
               now: datetime) -> PartsPlan:
    scope.validate()
    if scope.serial_required:
        # InventoryItems on-hand aggregate is insufficient to identify or
        # reserve a unique serial. Until InventoryItemSerialNumbers read and
        # allocation are governed, never assume serialized stock is usable.
        return PartsPlan(scope.request_id,scope.fingerprint,None,0,scope.quantity,
                         'blocked_serial_inventory_confirmation_required')
    if stock is None:
        return PartsPlan(scope.request_id,scope.fingerprint,None,0,scope.quantity,
                         'blocked_missing_authoritative_stock_readback')
    if (stock.product_id!=scope.product_id or
            stock.inventory_location_id!=scope.inventory_location_id):
        raise PartsLifecycleError('Autotask stock evidence is for wrong product/location')
    available=stock.available(now=now)
    candidate=min(scope.quantity,available)
    # Never subtract a "reserved" quantity until a real reservation/transfer
    # API returns a provider receipt. This is a PLAN, not a stock mutation.
    return PartsPlan(scope.request_id,scope.fingerprint,stock.source_sha256,
        candidate,scope.quantity-candidate,'pending_provider_stock_reservation'
        if candidate else 'stock_shortage_requires_purchase_approval')


def split_parts_plan(scope:PartsScope, plan:PartsPlan)->tuple[PartsScope,...]:
    """Create exact non-overlapping child requests for mixed stock + PO.

    This is a pure plan; no reserved stock or PO is implied. Each child needs
    its own authoritative provider readback and canonical approval chain.
    """
    from dataclasses import replace
    scope.validate()
    if plan.request_id!=scope.request_id or plan.scope_sha256!=scope.fingerprint:
        raise PartsLifecycleError('parts plan scope changed')
    if (plan.stock_candidate_quantity<0 or plan.unfilled_quantity<0
            or plan.stock_candidate_quantity+plan.unfilled_quantity!=scope.quantity):
        raise PartsLifecycleError('planned allocation does not balance')
    children=[]
    if plan.stock_candidate_quantity:
        children.append(replace(scope,request_id=scope.request_id+'-stock',
                                quantity=plan.stock_candidate_quantity))
    if plan.unfilled_quantity:
        children.append(replace(scope,request_id=scope.request_id+'-po',
                                quantity=plan.unfilled_quantity))
    return tuple(children)


def require_po_authority(*, service: Any,approval_id: str | None,
                         submission: Mapping[str,Any],amount: Decimal,
                         effective_threshold: Decimal)->None:
    """One shared signed-Teams check for all stock-shortage purchase paths."""
    amount=money(amount);effective_threshold=money(effective_threshold)
    if amount>effective_threshold:
        require_signed_purchase_approval(service=service,approval_id=approval_id or '',
                                         submission=submission)


@dataclass(slots=True)
class SQLitePartsLifecycleLedger:
    path: Path

    def __post_init__(self)->None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path,timeout=12) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS parts_requests (
                    request_id TEXT PRIMARY KEY, scope_json TEXT NOT NULL,
                    scope_sha256 TEXT NOT NULL, state TEXT NOT NULL,
                    received_count INTEGER NOT NULL DEFAULT 0,
                    installed_count INTEGER NOT NULL DEFAULT 0,
                    allocated_count INTEGER NOT NULL DEFAULT 0,
                    provider_po_id INTEGER, provider_charge_id INTEGER,
                    last_evidence_id TEXT, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS parts_events (
                    event_id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
                    scope_sha256 TEXT NOT NULL, event_type TEXT NOT NULL,
                    evidence_id TEXT NOT NULL, provider_resource_id INTEGER,
                    payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES parts_requests(request_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_parts_request_one_charge
                    ON parts_requests(provider_charge_id)
                    WHERE provider_charge_id IS NOT NULL;
                -- PO headers may contain multiple validated line requests.
                -- Per-line PO references remain immutable once recorded.
            ''')
        os.chmod(self.path,0o600)

    def create(self,scope: PartsScope,*,now:datetime)->dict[str,Any]:
        scope.validate()
        if now.tzinfo is None:raise PartsLifecycleError('UTC-aware event clock required')
        body=json.dumps(asdict(scope),sort_keys=True,separators=(',',':'))
        with sqlite3.connect(self.path,timeout=12) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT scope_sha256 FROM parts_requests WHERE request_id=?',(scope.request_id,)).fetchone()
            if row is not None:
                if row[0]!=scope.fingerprint:
                    raise PartsLifecycleError('request reuse with changed ticket/vendor/product/scope')
                return self.read(scope.request_id)
            db.execute('''INSERT INTO parts_requests
                (request_id,scope_json,scope_sha256,state,updated_at) VALUES(?,?,?,?,?)''',
                (scope.request_id,body,scope.fingerprint,'requested',now.astimezone(timezone.utc).isoformat()))
        return self.read(scope.request_id)

    def read(self,request_id:str)->dict[str,Any]|None:
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            row=db.execute('SELECT * FROM parts_requests WHERE request_id=?',(request_id,)).fetchone()
        return dict(row) if row is not None else None

    def events(self,request_id:str)->tuple[dict[str,Any],...]:
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            rows=db.execute('SELECT * FROM parts_events WHERE request_id=? ORDER BY rowid',(request_id,)).fetchall()
        return tuple(dict(r) for r in rows)

    def record(self,*,request_id:str,event_id:str,event_type:str,
               evidence_id:str,provider_resource_id:int|None,
               payload:Mapping[str,Any],at:datetime,
               approval_service:Any|None=None,approval_id:str|None=None,
               procurement_submission:Mapping[str,Any]|None=None)->dict[str,Any]:
        if event_type not in _ALLOWED_EVENTS:
            raise PartsLifecycleError('unreviewed parts movement event')
        require_identity(event_id,name='idempotent event')
        require_identity(evidence_id,name='verified provider evidence')
        if (provider_resource_id is not None
                and (type(provider_resource_id) is not int or provider_resource_id<1)):
            raise PartsLifecycleError('provider readback requires positive ID')
        if not isinstance(at,datetime) or at.tzinfo is None:
            raise PartsLifecycleError('aware readback clock required')
        body=dict(payload)
        fingerprint=digest(body)
        with sqlite3.connect(self.path,timeout=12,isolation_level=None) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                previous=db.execute('SELECT request_id,event_type,evidence_id,provider_resource_id,payload_sha256 FROM parts_events WHERE event_id=?',(event_id,)).fetchone()
                if previous is not None:
                    if previous!=(request_id,event_type,evidence_id,provider_resource_id,fingerprint):
                        raise PartsLifecycleError('replayed event ID with changed provider evidence')
                    db.execute('COMMIT')
                    current=self.read(request_id)
                    if current is None:raise PartsLifecycleError('parts request vanished')
                    return current
                row=db.execute('''SELECT scope_json,scope_sha256,state,received_count,
                    installed_count,allocated_count,provider_po_id,provider_charge_id
                    FROM parts_requests WHERE request_id=?''',(request_id,)).fetchone()
                if row is None:raise PartsLifecycleError('unregistered ticket/part request')
                scope=PartsScope(**json.loads(row[0]));scope.validate()
                if row[1]!=scope.fingerprint:
                    raise PartsLifecycleError('parts scope altered after request')
                state,received,installed,allocated,po_id,charge_id=row[2:]
                next_state=self._next_state(state,event_type)
                qty=body.get('quantity',0)
                if event_type in {'partial_received','received','installed','returned','stock_reserved','assigned'}:
                    if type(qty) is not int or qty<1 or qty>scope.quantity:
                        raise PartsLifecycleError('movement requires bounded positive quantity')
                if event_type=='stock_checked':
                    if (provider_resource_id is None
                            or body.get('source')!='autotask.inventory.items.read'
                            or body.get('scope_sha256')!=scope.fingerprint
                            or not isinstance(body.get('source_sha256'),str)
                            or not _SHA.fullmatch(body['source_sha256'])):
                        raise PartsLifecycleError('only verified Autotask inventory snapshot is accepted')
                if event_type=='stock_reserved':
                    if (body.get('source')!='autotask.inventory.readback'
                            or body.get('ticket_id')!=scope.ticket_id
                            or body.get('inventory_location_id')!=scope.inventory_location_id
                            or provider_resource_id is None):
                        raise PartsLifecycleError('stock allocation requires actual Autotask reservation readback')
                if event_type=='stock_reserved':
                    before=body.get('quantity_reserved_before')
                    after=body.get('quantity_reserved_after')
                    if (type(before) is not int or type(after) is not int
                            or before<0 or after-before!=qty):
                        raise PartsLifecycleError('provider reservation readback did not confirm exact reserved delta')
                    allocated+=qty
                    if allocated+received>scope.quantity:
                        raise PartsLifecycleError('provider stock reservation exceeds required quantity')
                if event_type=='purchase_approved':
                    if (body.get('source')!='signed_teams_approval'
                            or not body.get('approval_receipt_sha256')
                            or not _SHA.fullmatch(str(body['approval_receipt_sha256']))
                            or approval_id is None or procurement_submission is None):
                        raise PartsLifecycleError('purchase approval requires signed canonical Teams receipt')
                    receipt=require_signed_purchase_approval(
                        service=approval_service,approval_id=approval_id,
                        submission=procurement_submission)
                    if (body['approval_receipt_sha256']!=receipt.authentication_evidence_hash
                            or body.get('submission_digest')!=procurement_submission.get('digest')):
                        raise PartsLifecycleError('purchase receipt scope or signed hash mismatched')
                if event_type=='po_created':
                    if (procurement_submission is None
                            or procurement_submission.get('requester_principal_id')!=scope.requester_identity_id
                            or procurement_submission.get('ticket_id')!=scope.ticket_id
                            or procurement_submission.get('ticket_company_id')!=scope.company_id
                            or procurement_submission.get('spending_authority_source')
                                != 'autotask_contact_udf:Spending limit'
                            or procurement_submission.get('digest')!=body.get('submission_digest')):
                        raise PartsLifecycleError('provider PO lacks same-scope authenticated procurement submission')
                    udf=money(procurement_submission.get('spending_limit'))
                    threshold=money(procurement_submission.get('effective_spending_threshold') or udf)
                    if threshold>udf:
                        raise PartsLifecycleError('purchase threshold exceeds verified Autotask technician UDF')
                    require_po_authority(service=approval_service,approval_id=approval_id,
                        submission=procurement_submission,
                        amount=money(procurement_submission.get('total_commitment')),
                        effective_threshold=threshold)
                    if (body.get('source')!='autotask.purchase.order.readback'
                            or provider_resource_id is None
                            or body.get('ticket_id')!=scope.ticket_id
                            or body.get('company_id')!=scope.company_id):
                        raise PartsLifecycleError('PO must be verified and ticket/company linked')
                    if po_id is not None and po_id!=provider_resource_id:
                        raise PartsLifecycleError('duplicate provider purchase order')
                    po_id=provider_resource_id
                if event_type in {'partial_received','received'}:
                    if (body.get('source')!='autotask.purchase.order.receiving.readback'
                            or provider_resource_id is None
                            or po_id is None or body.get('purchase_order_id')!=po_id):
                        raise PartsLifecycleError('receipt requires verified matching Autotask PO')
                    received+=qty
                    if received>scope.quantity:raise PartsLifecycleError('received quantity exceeds ordered quantity')
                    next_state='received' if received==scope.quantity else 'partially_received'
                if event_type=='installed':
                    if body.get('ticket_id')!=scope.ticket_id:
                        raise PartsLifecycleError('installation must match exact ticket')
                    if scope.serial_required and not body.get('serial_number'):
                        raise PartsLifecycleError('serialized product requires serial evidence')
                    installed+=qty
                    if installed>received+allocated:
                        raise PartsLifecycleError('cannot install more than received or verified reserved')
                if event_type=='ticket_charged':
                    if (body.get('source')!='autotask.ticket.charge.readback'
                            or body.get('ticket_id')!=scope.ticket_id
                            or body.get('company_id')!=scope.company_id
                            or provider_resource_id is None):
                        raise PartsLifecycleError('ticket charge must have exact Autotask readback')
                    if charge_id is not None and charge_id!=provider_resource_id:
                        raise PartsLifecycleError('duplicate ticket charge')
                    charge_id=provider_resource_id
                if event_type in {'staged','assigned','returned'}:
                    if not body.get('location') or not body.get('technician_identity_id'):
                        raise PartsLifecycleError('movements require Teams-visible location and technician')
                if event_type=='assigned':
                    # The existing canonical release gate requires a billed
                    # ticket charge or a separately evidenced no-charge reason.
                    disposition='charge_created' if charge_id is not None else body.get('billing_disposition')
                    if charge_id is None and (
                        disposition not in {'no_charge_contract','no_charge_warranty','no_charge_internal'}
                        or body.get('billing_evidence_source')!='autotask.ticket.billing.readback'
                        or not isinstance(body.get('billing_evidence_sha256'),str)
                        or not _SHA.fullmatch(body['billing_evidence_sha256'])):
                        raise PartsLifecycleError('assignment must have verified ticket billing disposition')
                    try:
                        ReleaseGate(received_quantity=received+allocated,
                            release_quantity=qty,customer_quantity=scope.quantity,
                            ticket_id=scope.ticket_id,billing_disposition=disposition).validate()
                    except ProcurementControlError as exc:
                        raise PartsLifecycleError(str(exc)) from exc
                if event_type=='returned':
                    if (body.get('source')!='autotask.inventory.return.readback'
                            or provider_resource_id is None):
                        raise PartsLifecycleError('return requires verified Autotask inventory update')
                db.execute('''INSERT INTO parts_events VALUES (?,?,?,?,?,?,?,?,?)''',
                    (event_id,request_id,row[1],event_type,evidence_id,provider_resource_id,
                     json.dumps(body,sort_keys=True,separators=(',',':')),fingerprint,
                     at.astimezone(timezone.utc).isoformat()))
                db.execute('''UPDATE parts_requests SET state=?,received_count=?,
                    installed_count=?,allocated_count=?,provider_po_id=?,provider_charge_id=?,
                    last_evidence_id=?,updated_at=? WHERE request_id=?''',
                    (next_state,received,installed,allocated,po_id,charge_id,evidence_id,
                     at.astimezone(timezone.utc).isoformat(),request_id))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
        current=self.read(request_id)
        if current is None:raise PartsLifecycleError('parts request vanished')
        return current

    @staticmethod
    def _next_state(state:str,event_type:str)->str:
        allowed={
            'requested':{'stock_checked':'stock_checked','cancelled':'cancelled','exception':'exception'},
            'stock_checked':{'stock_reserved':'stock_reserved','purchase_approved':'purchase_approved','po_created':'ordered','cancelled':'cancelled','exception':'exception'},
            'stock_reserved':{'staged':'staged','assigned':'assigned','ticket_charged':'stock_reserved','cancelled':'cancelled','exception':'exception'},
            'purchase_approved':{'po_created':'ordered','cancelled':'cancelled','exception':'exception'},
            'ordered':{'partial_received':'partially_received','received':'received','cancelled':'cancelled','exception':'exception'},
            'partially_received':{'partial_received':'partially_received','received':'received','exception':'exception'},
            'received':{'staged':'staged','assigned':'assigned','ticket_charged':'received','returned':'returned','exception':'exception'},
            'staged':{'assigned':'assigned','ticket_charged':'staged','returned':'returned','exception':'exception'},
            'assigned':{'installed':'installed','returned':'returned','exception':'exception'},
            'installed':{'ticket_charged':'installed','returned':'returned','exception':'exception'},
            'returned':{'cancelled':'cancelled','exception':'exception'},
            'exception':{'cancelled':'cancelled'},
        }
        next_state=allowed.get(state,{}).get(event_type)
        if next_state is None:
            raise PartsLifecycleError(f'illegal parts lifecycle transition: {state}->{event_type}')
        return next_state
