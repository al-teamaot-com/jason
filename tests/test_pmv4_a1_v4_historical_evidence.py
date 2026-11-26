"""Offline behavioral tests for A1 v4's two-history root admission guards."""
from __future__ import annotations

import ast
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

from tools import pmv4_a1_v4_immutable_builder as builder

SOURCE = "e" * 40
IMAGE = "sha256:" + "d" * 64
V1_APPROVAL = builder.ORIGINAL_APPROVAL
V3_APPROVAL = builder.PREVIOUS_V3_APPROVAL
V1_SOURCE = builder.ORIGINAL_SOURCE
V3_SOURCE = builder.PREVIOUS_V3_SOURCE
EMPTY = "0" * 40


def generated_function(name, globals_map):
    root = builder.render_root(
        Path(builder.FILES[0]).read_text(), SOURCE, IMAGE)
    module = ast.parse(root)
    fn = next(x for x in module.body
              if isinstance(x, ast.FunctionDef) and x.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    scope = dict(globals_map)
    exec(compile(module, "<synthetic-reviewed-root>", "exec"), scope)
    return scope[name]


def root_metadata(monkeypatch, root):
    original_lstat = Path.lstat

    def root_lstat(path):
        observed = original_lstat(path)
        if path == root or root in path.parents:
            return SimpleNamespace(
                st_uid=0, st_nlink=observed.st_nlink,
                st_mode=observed.st_mode, st_size=observed.st_size)
        return observed

    monkeypatch.setattr(Path, "lstat", root_lstat)


def root_context(tmp_path, monkeypatch):
    root = tmp_path / "shadow"
    for relative in ("control", "releases", "receipts"):
        (root / relative).mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    for relative in ("control", "releases", "receipts"):
        (root / relative).chmod(0o700)
    (root / "releases" / EMPTY).mkdir(mode=0o700)
    (root / "current").symlink_to("releases/" + EMPTY)
    docs = {
        V1_APPROVAL: {
            "approval_id": V1_APPROVAL, "candidate_sha": V1_SOURCE,
            "rollback_sha": EMPTY, "state": "rolled_back"},
        V3_APPROVAL: {
            "approval_id": V3_APPROVAL, "candidate_sha": V3_SOURCE,
            "rollback_sha": EMPTY, "state": "rolled_back",
            "reconciled": True},
    }
    for approval, doc in docs.items():
        f = root / "receipts" / ("owner-" + approval + ".json")
        f.write_text(json.dumps(doc))
        f.chmod(0o600)
    root_metadata(monkeypatch, root)
    return root, docs


def test_exactly_two_rolled_back_receipts_admitted_with_empty_runtime(
    tmp_path, monkeypatch
):
    root, _ = root_context(tmp_path, monkeypatch)
    class Adapter:
        def __init__(self, **kwargs):
            pass
        def _owned_or_absent(self):
            return None
    scope = dict(
        ROOT=root, CURRENT=root / "current", ROLLBACK=EMPTY,
        TARGET=root / "releases" / SOURCE,
        APPROVED=root / "control" / "approved-manifest.json",
        REVIEWED=root / "control" / "reviewed-scope.json",
        TOKEN=root / "control" / "gateway-token",
        AUDIT=root / "control" / "a1-exact-atomic-bootstrap-v4-test.jsonl",
        need=lambda ok, code: None if ok else (_ for _ in ()).throw(
            PermissionError(code)),
        shadow=SimpleNamespace(read_json=lambda p: json.loads(p.read_text())),
        docker_shadow=SimpleNamespace(DockerShadowAdapter=Adapter),
        exact_docker_29_compat_runner=lambda *a, **kw: None,
        stat=stat, os=__import__("os"),
    )
    scope["AUDIT"] = root / "control" / "a1-exact-atomic-bootstrap-v4-test.jsonl"
    validate = generated_function("empty_baseline", scope)
    validate()

    # An expired/failed Owner transaction is never an allowed baseline.
    p = root / "receipts" / ("owner-" + V3_APPROVAL + ".json")
    record = json.loads(p.read_text())
    record["state"] = "started"
    p.write_text(json.dumps(record))
    with pytest.raises(PermissionError, match="HISTORICAL_OWNER_RECEIPT_NOT_RECONCILED"):
        validate()

    record["state"] = "rolled_back"
    p.write_text(json.dumps(record))
    (root / "receipts" / "extra.json").write_text("{}")
    with pytest.raises(PermissionError, match="EXACT_TWO_ROLLED_BACK_RECEIPTS_REQUIRED"):
        validate()


def audit_context(tmp_path, monkeypatch):
    root, docs = root_context(tmp_path, monkeypatch)
    audit = root / "control" / "a1-exact-atomic-bootstrap-v3-c999216a3df9.jsonl"
    events = ["begin", "intent-create-root", "created-file", "intent-create-file",
              "requires_review", "exact_owner_rollback_native_verified",
              "reconciled_original_exact_owner_rollback"]
    rows = []
    prev = "0" * 64
    for index, event in enumerate(events):
        row = {
            "index": index, "event": event,
            "source_sha": V3_SOURCE, "approval_id": V3_APPROVAL,
            "previous_sha256": prev, "details": {},
        }
        record_hash = sha256(canonical(row)).hexdigest()
        row["hash"] = record_hash
        rows.append(row)
        prev = record_hash
    audit.write_bytes(b"\n".join(canonical(row) for row in rows) + b"\n")
    audit.chmod(0o600)
    return root, rows, docs, audit


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def test_v3_rollback_audit_hash_chain_and_terminal_reconciliation(
    tmp_path, monkeypatch
):
    root, rows, docs, audit = audit_context(tmp_path, monkeypatch)
    proof = {"approval_id": V3_APPROVAL, "source_sha": V3_SOURCE}
    def read_json(p, **kwargs):
        if p == root / "receipts" / ("owner-" + V3_APPROVAL + ".json"):
            return docs[V3_APPROVAL]
        return proof
    scope = dict(
        ROOT=root, ROLLBACK=EMPTY, Path=Path, stat=stat, json=json,
        read_json=read_json, sha=lambda raw: sha256(raw).hexdigest(),
        canon=canonical, need=lambda ok, code: None if ok else (_ for _ in ()).throw(
            PermissionError(code)),
    )
    verify = generated_function("original_v3_rollback_audit", scope)
    verify()

    # A nonterminal root journal is not a verified release rollback.
    tampered = json.loads(audit.read_bytes().splitlines()[-1])
    tampered["event"] = "requires_review"
    tampered["hash"] = sha256(canonical({
        k: v for k, v in tampered.items() if k != "hash"
    })).hexdigest()
    lines = audit.read_bytes().splitlines()
    audit.write_bytes(b"\n".join(lines[:-1] + [canonical(tampered)]) + b"\n")
    with pytest.raises(PermissionError, match="PRIOR_V3_AUDIT_NOT_RECONCILED"):
        verify()

    # Any tampering that breaks the chain is denied even if terminal says OK.
    lines = audit.read_bytes().splitlines()
    audit.write_bytes(b"\n".join(lines[:-1] + [canonical(rows[-1])]) + b"\n")
    lines = audit.read_bytes().splitlines()
    corrupted = json.loads(lines[1])
    corrupted["event"] = "unexpected"
    lines[1] = canonical(corrupted)
    audit.write_bytes(b"\n".join(lines) + b"\n")
    with pytest.raises(PermissionError, match="PRIOR_V3_AUDIT_CHAIN_INVALID"):
        verify()


def test_v3_prior_receipt_not_reconciled_cannot_be_reused(tmp_path, monkeypatch):
    root, rows, docs, audit = audit_context(tmp_path, monkeypatch)
    docs[V3_APPROVAL]["state"] = "started"
    def read_json(p, **kwargs):
        if "receipts" in p.parts:
            return docs[V3_APPROVAL]
        return {"approval_id": V3_APPROVAL, "source_sha": V3_SOURCE}
    scope = dict(
        ROOT=root, ROLLBACK=EMPTY, Path=Path, stat=stat, json=json,
        read_json=read_json, sha=lambda raw: sha256(raw).hexdigest(),
        canon=canonical, need=lambda ok, code: None if ok else (_ for _ in ()).throw(
            PermissionError(code)),
    )
    verify = generated_function("original_v3_rollback_audit", scope)
    with pytest.raises(PermissionError, match="PRIOR_V3_RECEIPT_NOT_RECONCILED"):
        verify()
