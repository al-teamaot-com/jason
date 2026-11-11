"""Source-bound recovery of missing MCP builder base from immutable V2 LKG."""
import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest
import release_manager_host_runner as m

ORIGINAL = "jason-mcp:generic-governed-8f1e864947a2"
REV = "c43e88e072c0b35c5b342d5e712fe34565b3e0cd"
DIGEST = "sha256:013c3f6dc5ef566978960f026b475264c0e358fe3c8e86564986b017bcc3449d"
RUNTIME = "sha256:66606ecec03a094ac9de2dc794a6c063698f2e6e6d088e890fabbb479e0b18d7"
GENERIC = "sha256:d709ca54b66d41e22bd1f67782cd5f6d681c4337bffb359b632523762a27788a"
RECOVERY = "jason-mcp:attested-v2-c43e88e072c0-013c3f6dc5ef"


def missing(image):
    raise subprocess.CalledProcessError(1, ["docker", "inspect", image])


def control(state="closed", digest=DIGEST):
    return {"schema_version":"1.0",
            "circuit_breaker":{"state":state},
            "last_known_good":{"manifest":{
                "complete":True,"revision":REV,"mcp_image_id":digest,
                "runtime_image_id":RUNTIME}}}


def test_existing_immutable_generic_base_requires_no_fallback():
    with patch.object(m, "image_id", return_value=GENERIC) as image, \
         patch.object(m, "_read_protected_snapshot",
                      side_effect=AssertionError("root fallback not applicable")):
        ref, digest = m.verified_mcp_preproduction_base(Path("/tmp"))
    assert ref == ORIGINAL
    assert digest == GENERIC
    image.assert_called_once_with(ORIGINAL)


@pytest.mark.parametrize("state,digest", [
    ("open", DIGEST),
    ("closed", "sha256:" + "f"*64),
])
def test_fallback_denied_until_closed_breaker_and_exact_root_lkg(state, digest):
    with patch.object(m, "image_id", side_effect=missing), \
         patch.object(m, "_read_protected_snapshot", return_value=control(state,digest)), \
         patch.object(m, "run") as mutation:
        with pytest.raises(m.ReleaseManagerError, match="no root-attested V2"):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    mutation.assert_not_called()


def test_fallback_uses_pinned_digest_only_and_does_not_rewrite_original_base():
    def identify(ref):
        if ref == ORIGINAL or ref == RECOVERY:
            return missing(ref)
        if ref == DIGEST:
            return DIGEST
        raise AssertionError("unexpected image lookup "+ref)
    calls = []
    exists = {"new":False}
    def inspector(ref):
        if ref == RECOVERY and exists["new"]:
            return DIGEST
        return identify(ref)
    def tag(args):
        assert args == ["docker","tag",DIGEST,RECOVERY]
        calls.append(args)
        exists["new"]=True
    with patch.object(m, "image_id", side_effect=inspector), \
         patch.object(m, "_read_protected_snapshot", return_value=control()), \
         patch.object(m, "live_production_alignment", return_value={"mcp_revision":REV}), \
         patch.object(m, "live_mcp", return_value={"image_id":DIGEST}), \
         patch.object(m, "live_runtime", return_value={"image_id":RUNTIME}), \
         patch.object(m, "run", side_effect=tag):
        ref, digest = m.verified_mcp_preproduction_base(Path("/tmp"))
    assert (ref,digest) == (RECOVERY,DIGEST)
    assert len(calls)==1


def test_fallback_rejects_a_replaced_attested_tag():
    def image(ref):
        if ref == ORIGINAL:
            return missing(ref)
        if ref == DIGEST:
            return DIGEST
        if ref == RECOVERY:
            return "sha256:"+ "e"*64
        raise AssertionError(ref)
    with patch.object(m, "image_id", side_effect=image), \
         patch.object(m, "_read_protected_snapshot", return_value=control()), \
         patch.object(m, "live_production_alignment", return_value={"mcp_revision":REV}), \
         patch.object(m, "live_mcp", return_value={"image_id":DIGEST}), \
         patch.object(m, "live_runtime", return_value={"image_id":RUNTIME}), \
         patch.object(m, "run") as mutation:
        with pytest.raises(m.ReleaseManagerError, match="was replaced"):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    mutation.assert_not_called()


def test_fallback_cannot_use_unpinned_live_mcp_image():
    with patch.object(m, "image_id", side_effect=missing), \
         patch.object(m, "_read_protected_snapshot", return_value=control()), \
         patch.object(m, "live_production_alignment", return_value={"mcp_revision":REV}), \
         patch.object(m, "live_mcp", return_value={"image_id":"sha256:"+ "7"*64}), \
         patch.object(m, "run") as mutation:
        with pytest.raises(m.ReleaseManagerError, match="differs from live"):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    mutation.assert_not_called()


def test_source_never_forged_historical_base_tag():
    source=(Path(__file__).resolve().parents[1]/"release_manager_host_runner.py").read_text()
    assert "docker\", \"tag\", known_image, recovery" in source
    assert 'recovery = "jason-mcp:attested-v2-' in source
    assert 'verified_mcp_preproduction_base(state_root)' in source
    assert 'return canonical, canonical_observed' in source


def test_canonical_tag_substitution_is_rejected():
    with patch.object(m, "image_id", return_value="sha256:" + "c"*64), \
         patch.object(m, "_read_protected_snapshot") as snapshot:
        with pytest.raises(m.ReleaseManagerError, match="differs from pinned"):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    snapshot.assert_not_called()


def test_root_runtime_digest_substitution_denied():
    with patch.object(m, "image_id", side_effect=missing), \
         patch.object(m, "_read_protected_snapshot",
                      return_value={**control(), "last_known_good":{"manifest":{
                          "complete":True,"revision":REV,"mcp_image_id":DIGEST,
                          "runtime_image_id":"sha256:"+"0"*64}}}), \
         patch.object(m, "run") as mutation:
        with pytest.raises(m.ReleaseManagerError, match="no root-attested V2"):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    mutation.assert_not_called()


CURRENT_SHA = "e" * 40
CURRENT_MCP = "sha256:" + "b" * 64
CURRENT_RUNTIME = "sha256:" + "c" * 64
CURRENT_TAG = "jason-mcp:attested-lkg-" + CURRENT_SHA[:12] + "-" + CURRENT_MCP[7:19]


def current_control(*, state="closed", revalidated=True, mcp_id=CURRENT_MCP,
                    runtime_id=CURRENT_RUNTIME, mode="owner_reviewed"):
    return {
        "circuit_breaker": {
            "state": state,
            "revalidated_revision": CURRENT_SHA if revalidated else "a"*40,
        },
        "last_known_good": {"manifest": {
            "complete": True, "revision": CURRENT_SHA,
            "mcp_image_id": mcp_id, "runtime_image_id": runtime_id,
            "mobile_release_approval_mode": mode,
        }},
    }


def test_current_production_lkg_mcp_is_exact_pinned_preproduction_base():
    tagged = {"yes": False}
    changes = []

    def inspect(ref):
        if ref == ORIGINAL:
            raise subprocess.CalledProcessError(1, ["docker", "inspect", ref])
        if ref == CURRENT_TAG:
            if not tagged["yes"]:
                raise subprocess.CalledProcessError(1, ["docker", "inspect", ref])
            return CURRENT_MCP
        if ref in {CURRENT_MCP, CURRENT_RUNTIME}:
            return ref
        raise AssertionError("unexpected Docker image reference: " + ref)

    def tag(command):
        assert command == ["docker", "tag", CURRENT_MCP, CURRENT_TAG]
        tagged["yes"] = True
        changes.append(command)

    with patch.object(m, "image_id", side_effect=inspect), \
         patch.object(m, "_read_protected_snapshot", return_value=current_control()), \
         patch.object(m, "live_production_alignment", return_value={
             "mcp_revision": CURRENT_SHA, "runtime_revision": CURRENT_SHA,
         }), \
         patch.object(m, "live_mcp", return_value={"image_id": CURRENT_MCP}), \
         patch.object(m, "live_runtime", return_value={"image_id": CURRENT_RUNTIME}), \
         patch.object(m, "run", side_effect=tag):
        ref, digest = m.verified_mcp_preproduction_base(Path("/tmp"))

    assert (ref, digest) == (CURRENT_TAG, CURRENT_MCP)
    assert changes == [["docker", "tag", CURRENT_MCP, CURRENT_TAG]]


@pytest.mark.parametrize("change", [
    {"state": "open"}, {"revalidated": False},
    {"mcp_id": "invalid"}, {"runtime_id": "invalid"},
    {"mode": "teams_only"},
])
def test_current_production_base_requires_verified_closed_owner_lkg(change):
    with patch.object(m, "image_id", side_effect=missing), \
         patch.object(m, "_read_protected_snapshot",
                      return_value=current_control(**change)), \
         patch.object(m, "live_mcp") as mcp_read, \
         patch.object(m, "run") as mutation:
        with pytest.raises(m.ReleaseManagerError):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    mcp_read.assert_not_called()
    mutation.assert_not_called()


@pytest.mark.parametrize("variant", ["wrong_current_mcp", "wrong_current_runtime", "wrong_alignment"])
def test_current_base_refuses_protected_vs_live_mismatch(variant):
    mcp_id = "sha256:" + "d" * 64 if variant == "wrong_current_mcp" else CURRENT_MCP
    runtime_id = "sha256:" + "d" * 64 if variant == "wrong_current_runtime" else CURRENT_RUNTIME
    align = {
        "mcp_revision": "a" * 40 if variant == "wrong_alignment" else CURRENT_SHA,
        "runtime_revision": CURRENT_SHA,
    }
    def inspect(ref):
        if ref == ORIGINAL:
            raise subprocess.CalledProcessError(1, ["docker", "inspect", ref])
        if ref in {CURRENT_MCP, CURRENT_RUNTIME}:
            return ref
        raise AssertionError(ref)
    with patch.object(m, "image_id", side_effect=inspect), \
         patch.object(m, "_read_protected_snapshot", return_value=current_control()), \
         patch.object(m, "live_production_alignment", return_value=align), \
         patch.object(m, "live_mcp", return_value={"image_id": mcp_id}), \
         patch.object(m, "live_runtime", return_value={"image_id": runtime_id}), \
         patch.object(m, "run") as mutation:
        with pytest.raises(m.ReleaseManagerError, match="differs from live"):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    mutation.assert_not_called()


def test_current_lkg_attested_tag_substitution_fail_closed():
    def inspect(ref):
        if ref == ORIGINAL:
            raise subprocess.CalledProcessError(1, ["docker", "inspect", ref])
        if ref == CURRENT_TAG:
            return "sha256:" + "f"*64
        if ref in {CURRENT_MCP, CURRENT_RUNTIME}:
            return ref
        raise AssertionError(ref)
    with patch.object(m, "image_id", side_effect=inspect), \
         patch.object(m, "_read_protected_snapshot", return_value=current_control()), \
         patch.object(m, "live_production_alignment", return_value={
             "mcp_revision": CURRENT_SHA, "runtime_revision": CURRENT_SHA,
         }), \
         patch.object(m, "live_mcp", return_value={"image_id": CURRENT_MCP}), \
         patch.object(m, "live_runtime", return_value={"image_id": CURRENT_RUNTIME}), \
         patch.object(m, "run") as mutation:
        with pytest.raises(m.ReleaseManagerError, match="tag was replaced"):
            m.verified_mcp_preproduction_base(Path("/tmp"))
    mutation.assert_not_called()
