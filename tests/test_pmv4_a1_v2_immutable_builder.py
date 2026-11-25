"""New A1 release derived from protected source only, never prior approval."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from tools import pmv4_a1_v2_immutable_builder as b


HERE=Path(__file__).resolve().parents[1]
SOURCE="e"*40
IMAGE="sha256:"+"d"*64


def template(relative):
    return (HERE/relative).read_text()


def test_generated_root_is_versioned_and_rejects_old_owner_replay():
    source=template(b.FILES[0])
    text=b.render_root(source,SOURCE,IMAGE)
    compile(text,"<candidate-root>","exec")
    assert 'CANDIDATE="'+SOURCE+'"' in text
    assert 'IMAGE="'+IMAGE+'"' in text
    assert 'ACTION="'+b.NEW_ACTION+'"' in text
    assert 'bootstrap-v3-' in text
    assert '"/run/jason-pmv4-a1-v3-'+SOURCE[:12]+'/installer.py"' in text
    assert 'original_v2_rollback_audit()' in text
    assert 'preapproval_candidate_compose_pair(manifest)' in text
    assert 'native.ShadowController(' in text
    assert 'compose_binding="candidate"' in text
    assert 'legacy_compose_sha256="'+b.LEGACY_COMPOSE_SHA+'"' in text
    assert b.ORIGINAL_APPROVAL in text
    assert 'historical.get("state")=="rolled_back"' in text
    assert 'A1_V2_ORIGINAL_OWNER_RECEIPT_NOT_RECONCILED' in text
    assert '    source_git_attestation(plan)\n    original_v2_rollback_audit()\n    preapproval_candidate_compose_pair(manifest)\n    empty_baseline()' in text
    assert 'verified_reviewed_module("tools/pmv4_host_release_guard.py","guard")' in text
    assert 'verified_reviewed_module("tools/pmv4_shadow_docker_adapter.py","adapter")' in text
    assert 'exec(compile(body,"protected-main:"+CANDIDATE' in text
    assert 'sha(body)==plan["source_files"][relative]' in text
    assert 'issue_exact_owner_release(' not in text  # root may only verify proof
    # The original failure journal must remain immutable evidence.
    assert 'AUDIT=ROOT/"control"/"a1-exact-atomic-bootstrap.jsonl"' not in text


def test_issuer_imports_exact_generated_root_not_old_source_module():
    text=b.render_owner(template(b.FILES[1]),SOURCE)
    compile(text,"<candidate-owner>","exec")
    assert 'ROOT_GENERATED=Path(__file__).with_name(' in text
    assert 'from tools import pmv4_a1_atomic_shadow_root as root' not in text
    assert str(b.ARTIFACT_PARENT/("pmv4-a1-"+SOURCE)) in text
    assert "signer.issue_exact_owner_release" in text
    assert "APPROVE-ONE-EXACT-PMV4-A1-V3-DISCONNECTED-SHADOW" in text
    assert "APPROVE-ONE-EXACT-PMV4-A1-V2-DISCONNECTED-SHADOW" not in text
    assert "APPROVE-ONE-EXACT-PMV4-A1-DISCONNECTED-SHADOW-BOOTSTRAP" not in text
    assert 'root.CANDIDATE' in text


def test_local_launcher_is_exact_versioned_one_use():
    text=b.render_local(template(b.FILES[2]),SOURCE,"a"*64,"b"*64)
    assert 'ROOT_SHA="'+"a"*64+'"' in text
    assert 'OWNER_SHA="'+"b"*64+'"' in text
    assert 'SOURCE="'+SOURCE+'"' in text
    assert 'A1_V2_SOURCE_CHECKOUT_DIRTY' in text
    assert 'A1_V2_SOURCE_CHECKOUT_CHANGED' in text
    assert '"/run/jason-pmv4-a1-v3-'+SOURCE[:12]+'"' in text
    assert "sudo /usr/bin/python3 -I -B \"$STAGED\" --preflight" in text
    assert "sudo /usr/bin/python3 -I -B \"$STAGED\" --postflight" in text
    assert "OWNER_APPROVAL_CREATED=1" in text
    assert b.ORIGINAL_APPROVAL not in text  # previous consent not reused


@pytest.mark.parametrize("bad",["bad","f"*39,"g"*40])
def test_invalid_source_rejected(bad):
    with pytest.raises(b.CandidateBuildDenied,match="INVALID_SOURCE_OR_IMAGE|SHA_OR_IMAGE"):
        b.render_root(template(b.FILES[0]),bad,IMAGE)


def test_missing_or_duplicated_template_anchor_fails_closed():
    with pytest.raises(b.CandidateBuildDenied,
                       match="TEMPLATE_CONTEXT_NOT_EXACT"):
        b.render_root("source changed",SOURCE,IMAGE)
    with pytest.raises(b.CandidateBuildDenied,
                       match="TEMPLATE_CONTEXT_NOT_EXACT"):
        b.render_owner("no root import",SOURCE)


def test_packet_emits_new_only_in_disposable_folder(tmp_path,monkeypatch):
    parent=tmp_path/"artifacts"
    parent.mkdir()
    monkeypatch.setattr(b,"ARTIFACT_PARENT",parent)
    packet=parent/("pmv4-a1-"+SOURCE)
    packet.mkdir(mode=0o700)
    (packet/"release").mkdir()
    (packet/"evidence.json").write_text(json.dumps({
        "status":"preproduction_candidate_not_authorized",
        "source_sha":SOURCE,"image_digest":IMAGE,
    }))
    (packet/"release"/"release-manifest.json").write_text(json.dumps({
        "candidate_sha":SOURCE,"image_digest":IMAGE,
    }))
    def source(_repo,sha,relative):
        assert sha==SOURCE
        return template(relative)
    monkeypatch.setattr(b,"read_git",source)
    report=b.prepare(SOURCE,IMAGE,repo=HERE,verify_main=lambda x:x==SOURCE)
    assert report["previous_owner_approval_reused"] is False
    assert report["previous_v2_approval_reused"] is False
    assert report["previous_v2_approval_id"]==b.PREVIOUS_V2_APPROVAL
    assert report["production_mutations"] is False
    assert report["gateway_started"] is False
    assert report["source_approval_issued"] is False
    assert report["previous_approval_id"]==b.ORIGINAL_APPROVAL
    assert report["root_executor_sha256"]==sha256(
        (packet/"tools"/"pmv4_a1_atomic_shadow_root.py").read_bytes()).hexdigest()
    assert report["owner_issuer_sha256"]==sha256(
        (packet/"tools"/"pmv4_a1_atomic_one_owner.py").read_bytes()).hexdigest()
    assert (packet/"evidence.json").is_file()
    assert not (packet/"root-oneowner-proof.json").exists()
    with pytest.raises(b.CandidateBuildDenied,match="ALREADY_GENERATED"):
        b.prepare(SOURCE,IMAGE,repo=HERE,verify_main=lambda _:True)


def test_wrong_approval_or_unverified_main_fails_before_creation(tmp_path,monkeypatch):
    parent=tmp_path/"artifacts"
    parent.mkdir()
    monkeypatch.setattr(b,"ARTIFACT_PARENT",parent)
    with pytest.raises(b.CandidateBuildDenied,match="MAIN_CHECKS_NOT_PASS"):
        b.prepare(SOURCE,IMAGE,verify_main=lambda _:False)
    assert list(parent.iterdir())==[]
    with pytest.raises(b.CandidateBuildDenied,match="SOURCE_PACKET_NOT_PREPARED"):
        b.prepare(SOURCE,IMAGE,verify_main=lambda _:True)
    assert list(parent.iterdir())==[]
