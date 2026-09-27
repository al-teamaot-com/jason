#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,tempfile
from datetime import datetime,timezone
from pathlib import Path

DEFAULT=Path("/var/lib/jason/ccc/material-review.json")

def main()->int:
    p=argparse.ArgumentParser(description="Record exact owner review for a material CCC source revision.")
    p.add_argument("--source-revision",required=True)
    p.add_argument("--recorded-by",required=True)
    p.add_argument("--reason",required=True)
    p.add_argument("--output",type=Path,default=DEFAULT)
    a=p.parse_args()
    rev=a.source_revision.strip().lower()
    if len(rev)!=40 or any(ch not in "0123456789abcdef" for ch in rev):
        raise SystemExit("source revision must be a full Git SHA")
    payload={"schema_version":"1.0","status":"approved","source_revision":rev,"recorded_by":a.recorded_by,"reason":a.reason,"recorded_at":datetime.now(timezone.utc).isoformat()}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".material-review-",suffix=".json",dir=a.output.parent)
    tmp=Path(name)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as h:
            json.dump(payload,h,indent=2,sort_keys=True); h.write("\n"); h.flush(); os.fsync(h.fileno())
        os.replace(tmp,a.output); os.chmod(a.output,0o600)
    finally:
        if tmp.exists(): tmp.unlink()
    print("CCC_MATERIAL_REVIEW=RECORDED")
    print(f"SOURCE_REVISION={rev}")
    print(f"OUTPUT={a.output}")
    return 0

if __name__=="__main__": raise SystemExit(main())
