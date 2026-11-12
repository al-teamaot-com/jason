"""Existing root reconciler accepts only explicit bounded signed A0 requests.

Ordinary host reconcile remains untouched. These source tests use a synthetic
operator-owned private request spool and never invoke a real root service.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

PATH = Path(__file__).resolve().parents[1] / "tools/release_host_reconcile_worker.py"
SPEC = importlib.util.spec_from_file_location("pmv4_source_only_root_worker", PATH)
assert SPEC is not None and SPEC.loader is not None
root_worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(root_worker)


@pytest.fixture
def a0_request(tmp_path, monkeypatch):
    monkeypatch.setattr(
        root_worker.pwd, "getpwnam",
        lambda name: SimpleNamespace(pw_uid=os.geteuid()),
    )
    path = tmp_path / "pmv4-stage-a0-request.json"
    payload = {
        "request_id": path.stem,
        "source_revision": "f"*40,
        "action": "pmv4_stage_a0_install",
        "scope_sha256": "a"*64,
        "manifest_sha256": "b"*64,
        "freeze_sha256": "c"*64,
        "signed_owner_proof": {"payload": {}, "signature_base64url": "bad"},
    }
    def save(value=payload):
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return path
    return payload, save


def test_exact_signed_a0_request_parses_to_narrow_kind(a0_request):
    payload, save = a0_request
    result = root_worker._read_request(save())
    assert result == payload


@pytest.mark.parametrize("mutation", [
    "missing_proof", "wrong_mode", "unexpected_field", "wrong_hash",
    "unknown_operation", "unrecognized_signed_object",
])
def test_a0_rejects_unbounded_operator_request(a0_request, mutation):
    payload, save = a0_request
    payload = payload.copy()
    if mutation == "missing_proof": payload.pop("signed_owner_proof")
    if mutation == "unexpected_field": payload["shell"] = "true"
    if mutation == "wrong_hash": payload["scope_sha256"] = "../../unsafe"
    if mutation == "unknown_operation": payload["action"] = "run_shell"
    if mutation == "unrecognized_signed_object": payload["signed_owner_proof"] = "text"
    path=save(payload)
    if mutation == "wrong_mode": path.chmod(0o644)
    with pytest.raises(root_worker.HostReconcileError):
        root_worker._read_request(path)


def test_ordinary_reconcile_still_uses_existing_path(a0_request):
    payload, save = a0_request
    ordinary = {
        "request_id": "pmv4-stage-a0-request",
        "source_revision": "a"*40,
    }
    assert root_worker._read_request(save(ordinary)) == ordinary


def test_root_worker_exact_a0_dispatch_never_invokes_host_redeploy(monkeypatch, a0_request):
    payload, save=a0_request
    calls=[]
    monkeypatch.setattr(root_worker, "_process_stage_a0_request",
                        lambda req: calls.append(("a0",req["scope_sha256"])) or {
                            "status": "installed",
                            "source_sha": req["source_revision"],
                            "rollback_sha": "0"*40,
                        })
    monkeypatch.setattr(root_worker, "_verify_main",
                        lambda sha: pytest.fail("ordinary host release path invoked"))
    monkeypatch.setattr(root_worker, "_mcp_revision",
                        lambda: pytest.fail("ordinary MCP deploy path invoked"))
    monkeypatch.setattr(root_worker, "_write_result",
                        lambda rid,sha,*,success,detail: calls.append(
                            ("receipt",success,detail)))
    root_worker._process(save())
    assert calls == [
        ("a0",payload["scope_sha256"]),
        ("receipt",True,"PMV4_STAGE_A0=" + json.dumps({
            "status": "installed",
            "source_sha": payload["source_revision"],
            "rollback_sha": "0"*40,
        }, sort_keys=True)),
    ]


def test_root_worker_recovered_empty_baseline_does_not_claim_install_success(
    monkeypatch, a0_request,
):
    payload, save = a0_request
    results = []
    monkeypatch.setattr(
        root_worker, "_process_stage_a0_request",
        lambda req: {
            "status": "empty_baseline_restored",
            "source_sha": req["source_revision"],
            "rollback_sha": "0"*40,
        },
    )
    monkeypatch.setattr(
        root_worker, "_write_result",
        lambda rid, sha, *, success, detail: results.append(
            (success, json.loads(detail.split("=", 1)[1])["status"])
        ),
    )
    monkeypatch.setattr(
        root_worker, "_mcp_revision",
        lambda: pytest.fail("ordinary redeploy incorrectly invoked"),
    )
    root_worker._process(save())
    assert results == [(False, "empty_baseline_restored")]
