#!/usr/bin/env python3
"""Read-only PMv4 Stage D continuity and schema migration evidence.

Never opens the live registry with SQLitePlaybookRegistry (that constructor
runs DDL). All migration acceptance is performed on an isolated consistent
SQLite backup using the already established registry and playbook validator.
Does not authorize playbooks, network requests or provider executions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Mapping

LIVE_DB = Path("/var/lib/jason/openclaw/json-playbooks.sqlite3")
REQUIRED = frozenset({
    "json_playbooks",
    "json_playbook_registry_meta",
    "json_playbook_lifecycle_events",
})


class RunbookReadbackDenied(RuntimeError):
    pass


def connection(db: Path) -> sqlite3.Connection:
    file=Path(db)
    if (not file.is_absolute() or ".." in file.parts or file.is_symlink()
        or not file.is_file()):
        raise RunbookReadbackDenied("JSON_REGISTRY_PATH_UNTRUSTED")
    info=file.stat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)&0o022:
        raise RunbookReadbackDenied("JSON_REGISTRY_METADATA_UNTRUSTED")
    try:
        con=sqlite3.connect("file:"+str(file)+"?mode=ro",
                            uri=True,timeout=4)
        con.execute("PRAGMA query_only=ON")
    except sqlite3.Error as exc:
        raise RunbookReadbackDenied("JSON_REGISTRY_READ_FAILED") from exc
    return con


def readback(db: Path, *, production: bool=False) -> dict[str,Any]:
    if production and Path(db) != LIVE_DB:
        raise RunbookReadbackDenied("JSON_REGISTRY_PRODUCTION_PATH_NOT_PINNED")
    con=connection(db)
    try:
        tables={row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        known=REQUIRED.intersection(tables)
        if not {"json_playbooks","json_playbook_registry_meta"}.issubset(tables):
            raise RunbookReadbackDenied("JSON_REGISTRY_BASE_SCHEMA_MISSING")
        generation_row=con.execute(
            "SELECT generation FROM json_playbook_registry_meta WHERE singleton=1"
        ).fetchone()
        if generation_row is None or type(generation_row[0]) is not int or generation_row[0]<0:
            raise RunbookReadbackDenied("JSON_REGISTRY_GENERATION_UNTRUSTED")
        generation=generation_row[0]
        total=con.execute("SELECT COUNT(*) FROM json_playbooks").fetchone()[0]
        active=con.execute(
            "SELECT COUNT(*) FROM json_playbooks WHERE state='active'"
        ).fetchone()[0]
        audit=None
        if "json_playbook_lifecycle_events" in tables:
            audit=con.execute(
                "SELECT COUNT(*) FROM json_playbook_lifecycle_events"
            ).fetchone()[0]
        duplicates=con.execute(
            "SELECT COUNT(*) FROM (SELECT playbook_id FROM json_playbooks "
            "WHERE state='active' GROUP BY playbook_id HAVING COUNT(*)>1)"
        ).fetchone()[0]
        quick=con.execute("PRAGMA quick_check").fetchone()
        if quick is None or quick[0]!="ok" or duplicates:
            raise RunbookReadbackDenied("JSON_REGISTRY_INTEGRITY_OR_ACTIVE_CONFLICT")
        if generation and (audit is None or audit != generation):
            raise RunbookReadbackDenied("JSON_REGISTRY_AUDIT_GENERATION_MISMATCH")
        ready=known==REQUIRED
        return {
            "status":"read_only_verified",
            "lifecycle_schema_ready":ready,
            "runbook_independent_management_operational":False,
            "generation":generation,
            "definitions":total,
            "active_definitions":active,
            "audit_events":audit,
            "required_tables_present":sorted(known),
            "required_tables_missing":sorted(REQUIRED-known),
            "immutable_version_conflicts":0,
            "provider_access":False,
            "owner_authorization_issued":False,
            "production_mutations":False,
        }
    except sqlite3.Error as exc:
        raise RunbookReadbackDenied("JSON_REGISTRY_READBACK_FAILED") from exc
    finally:
        con.close()


def isolated_upgrade_acceptance(db: Path) -> dict[str,Any]:
    """Prove code/runtime upgrade against a live-compatible COPY, never live DB."""
    before=Path(db).stat()
    con=connection(db)
    try:
        with tempfile.TemporaryDirectory(prefix="pmv4-d-registry-readonly-copy-") as tmp:
            clone=Path(tmp)/"json-playbooks.sqlite3"
            temp=sqlite3.connect(str(clone),timeout=4)
            try:
                con.backup(temp)
            finally:
                temp.close()
            from autonomous_remediation.playbook_store import SQLitePlaybookRegistry
            from tools.pmv4_runbook_lifecycle_acceptance import sample
            store=SQLitePlaybookRegistry(clone)
            try:
                existing=store.generation()
                pid="pmv4_acceptance_repair"
                # Never overwrite an existing exact synthetic ID on a copied
                # registry: no changes should become a source of truth.
                if any(x.document.playbook_id==pid for x in store.list_all()):
                    raise RunbookReadbackDenied("JSON_REGISTRY_COPY_SYNTHETIC_ID_COLLISION")
                staged=store.stage(sample(),actor="isolated-preproduction-acceptance")
                activated=store.activate(pid,staged.document.version,
                                          actor="isolated-preproduction-acceptance",
                                          expected_fingerprint=staged.document.fingerprint)
                retired=store.retire(pid,actor="isolated-preproduction-acceptance")
                if not retired or activated.state!="active" or store.generation()!=existing+3:
                    raise RunbookReadbackDenied("JSON_REGISTRY_COPY_LIFECYCLE_FAILURE")
                audit=len(store.lifecycle_events())
            finally:
                store.close()
            check=sqlite3.connect(str(clone))
            try: valid=check.execute("PRAGMA quick_check").fetchone()[0]
            finally:check.close()
            if valid!="ok":
                raise RunbookReadbackDenied("JSON_REGISTRY_COPY_INTEGRITY_FAILED")
    finally:
        con.close()
    after=Path(db).stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise RunbookReadbackDenied("JSON_REGISTRY_CHANGED_DURING_READ_ONLY_ACCEPTANCE")
    return {"status":"isolated_copy_accepted",
            "copied_lifecycle_operations":3,
            "copied_new_generation":existing+3,
            "copied_audit_events":audit,
            "live_registry_unchanged":True,
            "production_mutations":False,
            "owner_authorization_issued":False}


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--isolated-copy-acceptance",action="store_true")
    args=p.parse_args()
    if args.isolated_copy_acceptance:
        print(json.dumps(isolated_upgrade_acceptance(LIVE_DB),sort_keys=True))
    else:
        print(json.dumps(readback(LIVE_DB,production=True),sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
