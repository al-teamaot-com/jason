#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import sys
from uuid import uuid4

REPO=Path(__file__).resolve().parents[1]
IMPL=REPO/"implementation"
if str(IMPL) not in sys.path: sys.path.insert(0,str(IMPL))

from kernel.identity_authority import AuthorityGrant, IdentityRecord, PermissionMode, SQLiteAuthorityGrantRepository, SQLiteIdentityAuthorityStore, SQLiteIdentityRepository

DEFAULT_DB=Path("/var/lib/jason/authority/authority.sqlite3")
PRINCIPAL="jason-ccc-worker"
ORG="aot"
CAPABILITIES=(
    "service.ticket.search",
    "endpoint.device.read",
    "endpoint.security.status.read",
    "dns.protection.organization.read",
    "backup.endpoint.asset.search",
    "print.device.search",
    "identity.user.search",
    "system.registry.search",
)


def grant_id(capability:str)->str:
    return "grant-ccc-observe-"+capability.replace(".","-")


def expected_grant(capability:str)->AuthorityGrant:
    return AuthorityGrant(
        grant_id=grant_id(capability),
        subject_id=PRINCIPAL,
        capability=capability,
        organization_id=ORG,
        client_id=None,
        permission=PermissionMode.OBSERVE,
        approval_required=False,
        status="active",
    )


def same_grant(a:AuthorityGrant,b:AuthorityGrant)->bool:
    return asdict(a)==asdict(b)


def main()->int:
    p=argparse.ArgumentParser(description="Provision/check exact JKD-001 observe authority for the CCC worker.")
    p.add_argument("--database",type=Path,default=DEFAULT_DB)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--recorded-by",default="person-al")
    p.add_argument("--reason",default="Owner-approved CCC deterministic provider canaries")
    args=p.parse_args()
    store=SQLiteIdentityAuthorityStore(args.database)
    try:
        identities=SQLiteIdentityRepository(store)
        grants=SQLiteAuthorityGrantRepository(store)
        identity=identities.get(PRINCIPAL)
        expected_identity=IdentityRecord(PRINCIPAL,"service",ORG,"active")
        if identity is not None and identity != expected_identity:
            raise SystemExit("CCC_AUTHORITY=DENIED\nREASON=conflicting_identity")
        if identity is None:
            if not args.apply:
                raise SystemExit("CCC_AUTHORITY=NOT_PROVISIONED\nMISSING_IDENTITY=1")
            identities.put(expected_identity)
            store.append_authority_audit(
                event_type="authority.identity.recorded",
                correlation_id=f"corr_ccc_authority_{uuid4().hex}",
                principal_id=args.recorded_by,
                organization_id=ORG,
                capability="ccc.certification.run",
                outcome="recorded",
                reason_codes=(PRINCIPAL,args.reason),
            )
        missing=[]
        for capability in CAPABILITIES:
            wanted=expected_grant(capability)
            current=grants.get(wanted.grant_id)
            if current is not None and not same_grant(current,wanted):
                raise SystemExit(f"CCC_AUTHORITY=DENIED\nREASON=conflicting_grant\nGRANT_ID={wanted.grant_id}")
            if current is None:
                if not args.apply:
                    missing.append(capability)
                    continue
                grants.put(wanted)
                store.append_authority_audit(
                    event_type="authority.grant.recorded",
                    correlation_id=f"corr_ccc_authority_{uuid4().hex}",
                    principal_id=args.recorded_by,
                    organization_id=ORG,
                    capability=capability,
                    outcome="recorded",
                    reason_codes=(wanted.grant_id,"observe-only",args.reason),
                )
        if missing:
            print("CCC_AUTHORITY=NOT_PROVISIONED")
            for item in missing: print(f"MISSING_CAPABILITY={item}")
            return 2
        print("CCC_AUTHORITY=PASS")
        print(f"PRINCIPAL={PRINCIPAL}")
        print(f"OBSERVE_GRANTS={len(CAPABILITIES)}")
        return 0
    finally:
        store.close()

if __name__=="__main__": raise SystemExit(main())
