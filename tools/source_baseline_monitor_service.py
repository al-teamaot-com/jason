#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess
from pathlib import Path
try:
 from isolated_service_common import atomic_json,now_iso
except ModuleNotFoundError:
 from tools.isolated_service_common import atomic_json,now_iso

def git(repo:Path,*args:str)->str:
 r=subprocess.run(['git',*args],cwd=repo,capture_output=True,text=True,timeout=15,check=False)
 if r.returncode: raise RuntimeError(r.stderr.strip() or 'git failed')
 return r.stdout.strip()
def check(repo:Path,expected:str,ref:str='origin/main'):
 observed=git(repo,'rev-parse',ref)
 return {"status":"aligned" if observed==expected else "changed","expected_sha":expected,"observed_sha":observed,"ref":ref}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--expected-sha',required=True);p.add_argument('--ref',default='origin/main');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 result={"schema_version":"1.0","service":"source_baseline_monitor","observed_at":now_iso(),**check(a.repo,a.expected_sha,a.ref)};atomic_json(a.output,result);print(result['status']);return 0 if result['status']=='aligned' else 2
if __name__=='__main__': raise SystemExit(main())
