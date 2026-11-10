"""Source-bound recovery of missing MCP builder base from immutable V2 LKG."""
import subprocess
from pathlib import Path
from unittest.mock import patch
import pytest
import release_manager_host_runner as m

ORIGINAL = "jason-mcp:generic-governed-8f1e864947a2"
REV = "c43e88e072c0b35c5b342d5e712fe34565b3e0cd"
DIGEST = "sha256:013c3f6dc5ef566978960f026b475264c0e358fe3c8e86564986b017bcc3449d"
RECOVERY = "jason-mcp:attested-v2-c43e88e072c0-013c3f6dc5ef"


def missing(image):
    raise subprocess.CalledProcessError(1, ["docker", "inspect", image])


def control(state="closed", digest=DIGEST):
    return {"schema_version":"1.0",
            "circuit_breaker":{"state":state},
            "last_known_good":{"manifest":{
                "complete":True,"revision":REV,"mcp_image_id":digest}}}


def test_existing_immutable_generic_base_requires_no_fallback():
    with patch.object(m, "image_id", return_value="sha256:original") as image, \
         patch.object(m, "_read_protected_snapshot",
                      side_effect=AssertionError("root fallback not applicable")):
        ref, digest = m.verified_mcp_preproduction_base(Path("/tmp"))
    assert ref == ORIGINAL
    assert digest == "sha256:original"
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
    assert 'return canonical, image_id(canonical)' in source
