#!/usr/bin/env python3
"""Build a deterministic, *inert* Stage E root-admin installation handoff.

Unprivileged source-only: assembles reviewed Git tree bytes into one SHA-pinned
tar archive with root-owned metadata and a separate exact manifest. It neither
installs files nor issues an Owner proof nor modifies services. The authorized
host administrator must independently verify the archive and protected main,
apply it via an approved root-bootstrap boundary, and run the signed native
Stage E one-owner transaction; this output alone grants NO authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import stat
import tarfile

from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet

SHA=re.compile(r"^[0-9a-f]{40}$")
ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
ROOT="usr/local/lib/jason/pmv4-e-bootstrap/trusted"
MODE_FILE=0o444
MODE_DIR=0o555


class PackageDenied(PermissionError):
    pass


def need(ok,reason):
    if not ok:
        raise PackageDenied("PMV4_E_BOOTSTRAP_PACKET_"+reason)


def make_packet(*,candidate:str,rollback:str,
                output:Path,source_root:Path=packet.ROOT)->dict:
    need(type(candidate) is str and SHA.fullmatch(candidate) is not None
         and type(rollback) is str and SHA.fullmatch(rollback) is not None
         and candidate!=rollback,
         "RELEASE_IDENTITY_NOT_EXACT")
    need(output.is_absolute()
         and output.parent==ARTIFACTS
         and output.name==("pmv4-e-root-admin-bundle-"+candidate)
         and not output.exists() and not output.is_symlink(),
         "OUTPUT_NOT_UNIQUE_REVIEWED_PATH")
    need(Path(source_root).resolve()==packet.ROOT.resolve(),
         "MUTABLE_ALT_SOURCE_DIRECTORY_DENIED")
    reviewed=contract.draft(
        candidate_sha=candidate,rollback_sha=rollback,
        source_root=source_root)
    manifest=reviewed["manifest"]
    scope=reviewed["source_scope"]
    digests=scope["exact_replacement_files_sha256"]
    need(set(digests)==set(packet.REVIEWED_PATHS),
         "REVIEWED_FILE_SET_CHANGED")
    payloads={}
    for path in sorted(digests):
        raw=packet.read_reviewed(source_root,path)
        need(sha256(raw).hexdigest()==digests[path],
             "REVIEWED_BYTES_CHANGED")
        payloads[path]=raw
    output.mkdir(mode=0o700)
    archive=output/("stage-e-trusted-"+candidate+".tar")
    seen={ROOT}
    for rel in payloads:
        parts=rel.split("/")
        for index in range(1,len(parts)):
            seen.add(ROOT+"/"+"/".join(parts[:index]))
    # Reproducible tar metadata; extraction into system root still requires
    # a separately approved root administrator and independent SHA proof.
    with tarfile.open(archive,mode="w",format=tarfile.PAX_FORMAT) as tf:
        for name in sorted(seen,key=lambda p:(p.count("/"),p)):
            folder=tarfile.TarInfo(name+"/")
            folder.type=tarfile.DIRTYPE
            folder.mode=MODE_DIR
            folder.uid=folder.gid=0
            folder.uname=folder.gname="root"
            folder.mtime=0
            tf.addfile(folder)
        for rel,raw in sorted(payloads.items()):
            entry=tarfile.TarInfo(ROOT+"/"+rel)
            entry.mode=MODE_FILE
            entry.uid=entry.gid=0
            entry.uname=entry.gname="root"
            entry.size=len(raw)
            entry.mtime=0
            tf.addfile(entry,io.BytesIO(raw))
    archive.chmod(0o400)
    report={
        "schema_version":"1.0",
        "status":"source_only_no_root_install_or_release_authority",
        "candidate_sha":candidate,
        "rollback_sha":rollback,
        "action":packet.ACTION,
        "root_install_prefix":"/"+ROOT,
        "root_expected_uid":0,"root_expected_gid":0,
        "required_file_mode":"0444",
        "required_directory_mode":"0555",
        "reviewed_file_count":len(payloads),
        "reviewed_hashes":digests,
        "scope_sha256":manifest["source_scope_sha256"],
        "manifest_sha256":sha256(packet.canonical(manifest)).hexdigest(),
        "freeze_sha256":manifest["freeze_sha256"],
        "prior_root_policy_sha256":manifest["prior_root_policy_sha256"],
        "archive_sha256":sha256(archive.read_bytes()).hexdigest(),
        "native_six_unit_promotion_authorized":False,
        "owner_approval_issued":False,
        "production_mutations":False,
    }
    meta=output/"handoff-manifest.json"
    raw=packet.canonical(report)+b"\n"
    fd=os.open(meta,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o400)
    with os.fdopen(fd,"wb") as w:
        w.write(raw);w.flush();os.fsync(w.fileno())
    output.chmod(0o500)
    need(meta.read_bytes()==raw and
         sha256(archive.read_bytes()).hexdigest()==report["archive_sha256"],
         "PACKET_READBACK_MISMATCH")
    return {
        "status":report["status"],"candidate_sha":candidate,
        "reviewed_file_count":len(payloads),
        "archive_sha256":report["archive_sha256"],
        "scope_sha256":report["scope_sha256"],
        "manifest_sha256":report["manifest_sha256"],
        "artifacts_created":2,"owner_approval_issued":False,
        "production_mutations":False,
    }


def main(argv=None)->int:
    cli=argparse.ArgumentParser()
    cli.add_argument("--candidate-sha",required=True)
    cli.add_argument("--rollback-sha",required=True)
    args=cli.parse_args(argv)
    candidate=args.candidate_sha
    result=make_packet(
        candidate=candidate,rollback=args.rollback_sha,
        output=ARTIFACTS/("pmv4-e-root-admin-bundle-"+candidate))
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except (PackageDenied,PermissionError,ValueError,OSError) as exc:
        print("DENIED:"+type(exc).__name__,file=__import__("sys").stderr)
        raise SystemExit(2)
