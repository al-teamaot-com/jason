"""Fresh root CI evidence uses the pinned verifier and complete check pages."""
from pathlib import Path
import json
import os

import pytest

from tools import pmv4_e_ci_refresh as refresh

CANDIDATE = "a" * 40
HEAD = "b" * 40


def test_existing_pinned_verifier_loads_without_executing_root_actions(tmp_path):
    source = tmp_path / "verifier.py"
    source.write_bytes((Path(__file__).resolve().parents[1] /
                        "pmv4_e_canary_oneowner_root.py").read_bytes())
    source.chmod(0o444)
    module = refresh.load_pinned_attestor(source, production=False)
    assert callable(module["verify_ci"]) and callable(module["gh_api"])
    source.chmod(0o644)
    source.write_text("raise SystemExit('not trusted')")
    source.chmod(0o444)
    with pytest.raises(refresh.StageECIDenied, match="DIGEST_CHANGED"):
        refresh.load_pinned_attestor(source, production=False)


def test_full_required_check_projection_includes_all_pages():
    contexts = ["required-" + str(i) for i in range(8)]
    # Construct 210 rows with seven required checks on the final page.
    rows = [{"name": "noise-" + str(i)} for i in range(210)]
    rows[5] = {"name": contexts[0]}
    for i in range(1, 8):
        rows[200 + i] = {"name": contexts[i]}
    calls = []
    def original(endpoint, query):
        calls.append(endpoint)
        if endpoint == refresh.CHECK_POLICY:
            return {"strict": True, "checks": [{"context": x} for x in contexts]}
        page = int(endpoint.rsplit("=", 1)[1])
        return {"count": len(rows), "rows": rows[(page-1)*100:page*100]}
    namespace = {"gh_api": original}
    refresh.paginate_required_checks(namespace)
    namespace["gh_api"](refresh.CHECK_POLICY, "query")
    result = namespace["gh_api"]("repos/x/check-runs?per_page=100", "query")
    assert {x["name"] for x in result["rows"]} == set(contexts)
    assert result["count"] == 8
    assert calls[-1].endswith("&page=3")


@pytest.mark.parametrize("kind", ["no_policy", "missing_page", "changed_count", "duplicate_context"])
def test_incomplete_or_ambiguous_required_checks_fail_closed(kind):
    contexts = ["r" + str(i) for i in range(8)]
    def original(endpoint, query):
        if endpoint == refresh.CHECK_POLICY:
            names = contexts + ([contexts[0]] if kind == "duplicate_context" else [])
            return {"checks": [{"context": x} for x in names]}
        page = int(endpoint.rsplit("=", 1)[1])
        if kind == "missing_page":
            return {"count": 200, "rows": [{"name": "noise"}]}
        if kind == "changed_count":
            return {"count": 200 if page == 1 else 201,
                    "rows": [{"name": "noise"}] * 100}
        return {"count": 8, "rows": [{"name": x} for x in contexts]}
    namespace = {"gh_api": original}
    refresh.paginate_required_checks(namespace)
    with pytest.raises(refresh.StageECIDenied):
        if kind != "no_policy":
            namespace["gh_api"](refresh.CHECK_POLICY, "")
        namespace["gh_api"]("repos/x/check-runs?per_page=100", "")


def test_atomic_refresh_preserves_previous_evidence_and_permissions(tmp_path):
    tmp_path.chmod(0o700)
    target = tmp_path / "protected-ci.json"
    target.write_text('{"old":true}\n')
    target.chmod(0o400)
    evidence = {"candidate_sha": CANDIDATE, "required_ci_passed": True}
    archive = refresh.write_evidence(target, evidence, production=False)
    assert json.loads(target.read_bytes()) == evidence
    assert json.loads(Path(archive).read_bytes()) == {"old": True}
    assert target.stat().st_nlink == Path(archive).stat().st_nlink == 1
    assert target.stat().st_mode & 0o777 == 0o400
    assert not list(tmp_path.glob("*.tmp"))


def test_untrusted_existing_evidence_is_never_overwritten(tmp_path):
    tmp_path.chmod(0o700)
    other = tmp_path / "other"
    other.write_text("untouched")
    target = tmp_path / "protected-ci.json"
    target.symlink_to(other)
    with pytest.raises((OSError, PermissionError)):
        refresh.write_evidence(target, {"candidate_sha": CANDIDATE}, production=False)
    assert other.read_text() == "untouched" and target.is_symlink()


def test_denied_ci_does_not_replace_existing_evidence(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    target = tmp_path / "protected-ci.json"
    target.write_text('{"old":true}\n')
    target.chmod(0o400)
    namespace = {"gh_api": lambda *a: None,
                 "verify_ci": lambda _: {"candidate_sha": CANDIDATE,
                                          "required_ci_passed": False}}
    monkeypatch.setattr(refresh, "load_pinned_attestor", lambda *a, **kw: namespace)
    with pytest.raises(refresh.StageECIDenied, match="CI_NOT_VERIFIED"):
        refresh.refresh(CANDIDATE, production=False, source=tmp_path/"x", target=target)
    assert json.loads(target.read_text()) == {"old": True}


def test_production_cannot_override_installed_entry_or_files(tmp_path):
    with pytest.raises(refresh.StageECIDenied, match="ROOT_INSTALL_REQUIRED"):
        refresh.refresh(CANDIDATE, production=True, source=tmp_path/"x",
                        target=tmp_path/"protected-ci.json")


def test_original_ci_verifier_accepts_paginated_complete_required_set(tmp_path):
    from datetime import datetime, timezone
    source = tmp_path / "verifier.py"
    source.write_bytes((Path(__file__).resolve().parents[1] /
                        "pmv4_e_canary_oneowner_root.py").read_bytes())
    source.chmod(0o444)
    namespace = refresh.load_pinned_attestor(source, production=False)
    names = ["cap-001", "cap-003", "cap-007", "system-registry",
             "runtime-service", "repository-hygiene",
             "conversation-experience", "teams-gateway"]
    timestamp = datetime.now(timezone.utc).isoformat()
    checks = [{"name": "noise-" + str(i)} for i in range(210)]
    for i, name in enumerate(names):
        checks[200+i] = {
            "name": name, "sha": CANDIDATE, "status": "completed",
            "conclusion": "success", "app": 15368, "at": timestamp,
        }
    workflows = [
        {"name": name, "sha": CANDIDATE, "branch": "main", "event": "push",
         "status": "completed", "conclusion": "success", "at": timestamp}
        for name in ("Validate Jason", "SEC-007 Security Regressions",
                     "Validate Jason Teams Gateway",
                     "Validate Conversation Experience Foundation")
    ]
    def api(endpoint, query):
        if endpoint.endswith("/branches/main"):
            return {"name": "main", "protected": True, "sha": CANDIDATE}
        if "/compare/" in endpoint:
            return {"status": "identical", "merge_base_sha": CANDIDATE}
        if endpoint == refresh.CHECK_POLICY:
            return {"strict": True,
                    "checks": [{"context": x, "app_id": 15368} for x in names]}
        if "/check-runs?" in endpoint:
            page = int(endpoint.rsplit("=", 1)[1])
            return {"count": len(checks), "rows": checks[(page-1)*100:page*100]}
        if "/actions/runs?" in endpoint:
            return {"total": len(workflows), "rows": workflows}
        raise AssertionError(endpoint)
    namespace["gh_api"] = api
    refresh.paginate_required_checks(namespace)
    evidence = namespace["verify_ci"](CANDIDATE)
    assert evidence["candidate_sha"] == CANDIDATE
    assert evidence["required_ci_passed"] is True
    assert evidence["check_count"] == 8
    checks[201]["conclusion"] = "failure"
    with pytest.raises(PermissionError, match="NATIVE_REQUIRED_CHECK_NOT_SUCCESSFUL"):
        namespace["verify_ci"](CANDIDATE)
