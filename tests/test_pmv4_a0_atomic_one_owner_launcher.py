"""One true Owner Entra confirmation and root-only preflight before consent."""
from hashlib import sha256
from pathlib import Path
import subprocess

import pytest


ROOT=Path(__file__).parents[1]
LAUNCHER=ROOT/"tools/pmv4_a0_atomic_one_owner_local.sh"
ENTRY=ROOT/"tools/pmv4_a0_exact_v1_root_release.py"
BOOT=ROOT/"tools/pmv4_a0_closure_bootstrap_root.py"
OWNER=ROOT/"tools/pmv4_a0_atomic_v1_owner_issuer.py"
POLICY=ROOT/"config/pmv4-stage-a0/atomic-v1-root-policy-review.json"


def test_one_owner_prompt_after_root_only_preflight_no_human_before_it():
    script=LAUNCHER.read_text()
    assert script.count('"$OWNER" --authorize')==1
    assert script.count('"$OWNER" --verify-proof')==1
    assert script.count('"$STAGED" --preflight')==1
    assert script.count('"$STAGED" --execute')==1
    # Recovery is allowed in TWO failure windows: failed execute before
    # commit, and failed independent postflight after commit. Neither case
    # requires a second human Owner consent or signs a new release.
    assert script.count('"$STAGED" --recover')==2
    assert script.count('"$STAGED" --postflight')==1
    assert script.index('"$STAGED" --preflight')<script.index('"$OWNER" --authorize')
    assert script.index('"$OWNER" --authorize')<script.index('"$STAGED" --execute')
    assert 'PMV4_A0_NATIVE_STAGE_SEPARATE_APPROVAL' not in script
    assert 'ROOT_SHA=' in script and 'POLICY_SHA=' in script
    assert 'sudo /usr/bin/python3 -I -B "$STAGED"' in script
    assert 'COMPLETED=1' in script and 'trap cleanup EXIT' in script
    assert '"$CREATED" == 1 && "$APPROVAL_CREATED" == 0' in script
    assert '"$COMPLETED" == 1 )' not in script
    assert 'rollback-only and independent postflight must remain available' in script


def test_exact_reviewed_code_and_policy_hashes_were_pinned_by_owner_launcher():
    source=LAUNCHER.read_text()
    for path,key in ((ENTRY,"ROOT_SHA"),(BOOT,"BOOT_SHA"),
                     (OWNER,"OWNER_SHA"),(POLICY,"POLICY_SHA")):
        value=sha256(path.read_bytes()).hexdigest()
        assert key+'="'+value+'"' in source
    assert sha256(ENTRY.read_bytes()).hexdigest() in POLICY.read_text()


def test_launcher_denies_all_unsupported_modes_without_actions():
    assert subprocess.run(["bash","-n",str(LAUNCHER)],capture_output=True).returncode==0
    for mode in ("", "--run", "--recover", "--root-shell"):
        check=subprocess.run(["bash",str(LAUNCHER),mode],
                             capture_output=True,text=True)
        assert check.returncode==2
        assert "DENIED" in check.stderr


def test_owner_issuer_requires_one_real_interactive_authenticated_approval():
    issuer=OWNER.read_text()
    assert 'CONFIRM="APPROVE-ONE-EXACT-PMV4-A0-THREE-STAGE-ATOMIC-RELEASE"' in issuer
    assert issuer.count('signed=verifier.issue_exact_owner_release(')==1
    assert issuer.count('oid=device_owner_oid(oauth)')==1
    assert 'sys.stdin.isatty()' in issuer and 'sys.stdout.isatty()' in issuer
    assert 'os.O_EXCL' in issuer
    assert 'SIGNER=Path("/var/lib/jason/runtime-secrets/owner-release/private_key")' in issuer


@pytest.mark.skipif(
    not Path("/srv/jason/archive/pmv4-a0-closure-bootstrap-plan-7b42.json").is_file(),
    reason="live Jason host only",
)
def test_actual_unprivileged_local_check_uses_no_owner_approval():
    proc=subprocess.run(["bash",str(LAUNCHER),"--check-only"],
                        capture_output=True,text=True,timeout=45)
    assert proc.returncode==0,proc.stderr
    assert "OWNER_APPROVAL_CONSUMED=false" in proc.stdout
    assert "PRODUCTION_MUTATIONS=false" in proc.stdout


def test_current_main_bootstrap_journal_exactly_matches_reviewed_plan():
    """Regression: a signed plan may hash PASS yet fail root preflight if its journal differs."""
    import json
    from tools import pmv4_a0_closure_bootstrap_root as boot
    reviewed = ROOT / "config/pmv4-stage-a0/one-owner-recovery-review-20261115.json"
    contract = json.loads(reviewed.read_text())
    assert boot.PLAN == Path(contract["archived_bootstrap_plan_path"])
    assert boot.PLAN.name.endswith("8c20.json")
    assert boot.JOURNAL.name == "pmv4-a0-root-source-closure-bootstrap-8c20.json"
    if boot.PLAN.exists():
        plan, blobs = boot.validate_plan()
        assert plan["journal"] == str(boot.JOURNAL)
        assert len(blobs) == 2
