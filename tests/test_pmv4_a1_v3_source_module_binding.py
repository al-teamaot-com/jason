"""Avoid another signed Owner release reaching an untested native import path.

Dynamic execution occurs only with independently SHA-matched protected-source
bytes; these disposable tests do not access installed root trust or Docker.
"""
from hashlib import sha256
from pathlib import Path
import sys
import types

import pytest

from tools import pmv4_a1_v2_immutable_builder as b


SOURCE="a"*40
IMAGE="sha256:"+"b"*64


@pytest.fixture
def generated(tmp_path):
    source=Path(__file__).resolve().parents[1]
    root_text=b.render_root(
        (source/"tools/pmv4_a1_atomic_shadow_root.py").read_text(),
        SOURCE,IMAGE)
    r=types.ModuleType("tools.test_v3_generated_root")
    r.__file__=str(source/"tools/pmv4_a1_atomic_shadow_root.py")
    r.__package__="tools"
    exec(compile(root_text,r.__file__,"exec"),r.__dict__)
    archive=tmp_path/"archive"
    source_file=archive/"release"/"bundle"/"tools"/"pmv4_shadow_release.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes((source/"tools"/"pmv4_shadow_release.py").read_bytes())
    trusted=tmp_path/"trusted"
    (trusted/"tools").mkdir(parents=True)
    (trusted/"tools"/"pmv4_shadow_release.py").write_text(
        "not the code selected by this test\n")
    r.ARCHIVE=archive
    r.TRUSTED=trusted
    recorded=sha256(source_file.read_bytes()).hexdigest()
    r.plan_and_source=lambda:({"source_files":{
        "tools/pmv4_shadow_release.py":recorded}},{},{})
    return r,source_file,root_text,trusted


def test_native_dataclass_module_loads_only_reviewed_bytes(generated):
    r,file,code,trusted=generated
    before=list(sys.path)
    try:
        native=r.verified_reviewed_module("tools/pmv4_shadow_release.py","native")
        assert native.ShadowController is not None
        assert native.verify_shadow_compose_pair is not None
        assert native.__file__==str(trusted/"tools"/"pmv4_shadow_release.py")
        assert native.__a1_source_hash==sha256(file.read_bytes()).hexdigest()
        assert native.__name__ in sys.modules
        assert (trusted/"tools"/"pmv4_shadow_release.py").read_text()=="not the code selected by this test\n"
    finally:
        sys.path[:]=before
        sys.modules.pop("tools.pmv4_a1_v3_native",None)


def test_tampered_archive_module_is_denied_before_execution(generated):
    r,file,code,trusted=generated
    file.write_text("raise RuntimeError('should never execute')\n")
    with pytest.raises(r.A1RootDenied,match="A1_V2_REVIEWED_RUNTIME_MODULE_HASH_CHANGED"):
        r.verified_reviewed_module("tools/pmv4_shadow_release.py","native")


def test_module_namespace_collision_fails_closed(generated):
    r,file,code,trusted=generated
    foreign=types.ModuleType("tools.pmv4_a1_v3_native")
    sys.modules[foreign.__name__]=foreign
    try:
        with pytest.raises(r.A1RootDenied,
                           match="A1_V3_REVIEWED_MODULE_NAMESPACE_COLLISION"):
            r.verified_reviewed_module("tools/pmv4_shadow_release.py","native")
    finally:
        sys.modules.pop(foreign.__name__,None)


def test_preowner_root_preflight_includes_both_compose_and_historical_audit(generated):
    r,file,code,trusted=generated
    assert 'source_git_attestation(plan)\n    original_v2_rollback_audit()\n    preapproval_candidate_compose_pair(manifest)\n    empty_baseline()' in code
    assert 'native.verify_shadow_compose_pair(' in code
    assert 'legacy_compose_sha256="'+b.LEGACY_COMPOSE_SHA+'"' in code
    assert 'compose_binding="candidate"' in code
    assert "a1-exact-atomic-bootstrap-v3-" in code
    assert b.PREVIOUS_V2_APPROVAL in code
    assert 'rows[-1]["event"]=="rolled_back"' in code
    assert 'rows[-1]["event"]=="committed"' not in code.split(
        "def original_v2_rollback_audit()",1)[1].split(
        "def preapproval_candidate_compose_pair",1)[0]
    assert "issue_exact_owner_release(" not in code


def test_v3_issuer_and_launcher_do_not_reuse_v2_owner_confirmation(generated):
    r,file,code,trusted=generated
    source=Path(__file__).resolve().parents[1]
    issuer=b.render_owner((source/b.FILES[1]).read_text(),SOURCE)
    launcher=b.render_local((source/b.FILES[2]).read_text(),
                            SOURCE,"c"*64,"d"*64)
    assert b.NEW_ACTION in code
    assert "APPROVE-ONE-EXACT-PMV4-A1-V3-DISCONNECTED-SHADOW" in issuer
    assert "APPROVE-ONE-EXACT-PMV4-A1-V2-DISCONNECTED-SHADOW" not in issuer
    assert "/run/jason-pmv4-a1-v3-"+SOURCE[:12] in launcher
    assert "/srv/jason/archive/engineering-worktrees/pmv4-a1-v3-main-"+SOURCE[:12] in launcher
    assert b.PREVIOUS_V2_APPROVAL not in launcher
