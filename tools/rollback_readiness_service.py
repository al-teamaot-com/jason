#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any
try:
 from isolated_service_common import atomic_json,load_json,now_iso
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,load_json,now_iso

def evaluate(manifest:dict[str,Any])->dict[str,Any]:
 required=("rollback_sha","runtime_image","mcp_image","host_release")
 missing=[k for k in required if not str(manifest.get(k) or '').strip()]
 verified=bool(manifest.get('verified')) and not missing
 return {"status":"manifest_reported_verified" if verified else "not_ready","missing":missing,"rollback_sha":manifest.get('rollback_sha')}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();m=load_json(a.input)
 result={"schema_version":"1.0","service":"rollback_readiness","observed_at":now_iso(),**evaluate(m)};atomic_json(a.output,result);print(result['status']);return 0 if result['status']=='ready' else 2
if __name__=='__main__': raise SystemExit(main())
