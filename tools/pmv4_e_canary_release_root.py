#!/usr/bin/env python3
"""Source-only entrypoint for one authorized provider-free E canary release.

Installed variant must be root-owned, hash-pinned and independently verified
before invocation. Not a general release CLI and no Owner proof generation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

TRUSTED_ROOT=Path(
    "/opt/jason/independent-component-release/trusted/tools/"
    "pmv4_e_canary_release_root.py"
)
if os.geteuid()==0 and Path(__file__).resolve()==TRUSTED_ROOT:
    sys.path.insert(0,str(TRUSTED_ROOT.parent.parent))

from tools.independent_component_release import (
    ComponentReleaseController,ComponentReleaseDenied,
    PRODUCTION_ROOT,release_id,trusted_file,
)
from tools.pmv4_e_canary_host import PinnedCanaryHost
from tools import pmv4_e_canary_contract as contract

OWNER_OUTBOX=Path(
    "/var/lib/jason/openclaw/release-manager/"
    "independent-component-owner-approvals"
)
SHA=re.compile(r"^[0-9a-f]{40}$")


def deny(message):
    raise ComponentReleaseDenied("PMV4_E_CANARY_ROOT_"+message)


def exact_root():
    if (os.geteuid()!=0 or Path(__file__).resolve()!=TRUSTED_ROOT
        or not TRUSTED_ROOT.is_file() or TRUSTED_ROOT.is_symlink()):
        deny("INSTALLED_ROOT_ONLY")
    info=TRUSTED_ROOT.lstat()
    if info.st_uid!=0 or info.st_gid!=0 or stat.S_IMODE(info.st_mode)!=0o444:
        deny("ROOT_SCRIPT_MODE_CHANGED")


def invoke(sha:str):
    exact_root()
    if not isinstance(sha,str) or SHA.fullmatch(sha) is None:
        deny("SOURCE_NOT_SHA")
    manifest_path=PRODUCTION_ROOT/"releases"/sha/"manifest.json"
    manifest=json.loads(trusted_file(manifest_path,production=True,max_bytes=65536))
    if (manifest.get("candidate_sha")!=sha
        or manifest.get("component_id")!=contract.CANARY_ID
        or manifest.get("compose_project")!=contract.CANARY_PROJECT
        or manifest.get("image_digest")!=contract.IMAGE
        or manifest.get("provider_scope")!=contract.SCOPE
        or manifest.get("rollback_sha")!="0"*40):
        deny("SIGNED_SCOPE_NOT_PROVIDERFREE")
    approval_path=OWNER_OUTBOX/(release_id(sha)+".json")
    approval=json.loads(trusted_file(
        approval_path,production=True,allow_owner_write=True,
        allowed_uid=1000,max_bytes=32768))
    if (approval.get("release_id")!=release_id(sha)
        or approval.get("candidate_sha")!=sha
        or approval.get("component_id")!=contract.CANARY_ID
        or approval.get("image_digest")!=contract.IMAGE
        or approval.get("organization_id")!="aot"
        or not isinstance(approval.get("signed_owner_proof"),dict)):
        deny("SIGNED_OWNER_OUTBOX_SCOPE_INVALID")
    adapter=PinnedCanaryHost(production=True)
    controller=ComponentReleaseController(
        root=PRODUCTION_ROOT,production=True,
        host_transaction=adapter.host_transaction,
        freeze_transaction=adapter.freeze_transaction,
        verify_protected=adapter.protected,
        verify_source_and_ci=adapter.source_and_ci,
        verify_image=adapter.image,
        observe_component=adapter.observe,
        activate_component=adapter.activate,
        restore_component=adapter.restore,
        verify_component=adapter.verify_component,
    )
    result=controller.promote(manifest,approval["signed_owner_proof"])
    if (result.get("status")!="component_accepted"
        or result.get("candidate_sha")!=sha
        or result.get("component_id")!=contract.CANARY_ID
        or result.get("protected_services_changed") is not False):
        deny("NATIVE_GENERIC_CONTROLLER_ACCEPTANCE_MISSING")
    return {
        "status":"providerfree_native_generic_controller_accepted",
        "source_sha":sha,"component_id":contract.CANARY_ID,
        "image_digest":contract.IMAGE,
        "provider_writes":0,
        "protected_service_restarts":0,
        "retirement_authorized":False,
        "legacy_unit_changes":0,
    }


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--promote",action="store_true",required=True)
    parser.add_argument("--candidate-sha",required=True)
    args=parser.parse_args(argv)
    print(json.dumps(invoke(args.candidate_sha),sort_keys=True))


if __name__=="__main__":
    try:main()
    except (ComponentReleaseDenied,PermissionError,OSError,ValueError) as exc:
        print("PMV4_E_CANARY_ROOT_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:120] if isinstance(exc,ComponentReleaseDenied)
               else ""),file=sys.stderr)
        raise SystemExit(2)
