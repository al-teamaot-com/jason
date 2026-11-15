"""Ensure first exact Owner bootstrap cannot silently consume a second approval."""
from pathlib import Path
import subprocess

SOURCE = Path(__file__).parents[1] / "tools/pmv4_a0_bootstrap_only_owner_local.sh"
ORIGINAL = Path(__file__).parents[1] / "tools/pmv4_a0_closure_owner_local.sh"


def test_one_action_only_no_trailing_source_repair_or_native_install():
    script = SOURCE.read_text()
    assert "APPROVE-EXACT-PMV4-A0-CLOSURE-BOOTSTRAP" not in script
    assert 'python3 -B "$OWNER_SOURCE" --authorize' in script
    assert script.count('python3 -B "$OWNER_SOURCE" --authorize') == 1
    assert script.count('sudo /usr/bin/python3 -I "$STAGED" --execute') == 1
    assert 'sudo /usr/bin/python3 -I "$HELPER" --execute' not in script
    assert 'sudo /usr/bin/python3 -I "$TRUSTED_HELPER" --execute' not in script
    assert 'pmv4_stage_a_native_install.py' not in script
    assert 'STAGE_A0_SOURCE_REPAIR_AND_NATIVE_INSTALL=NOT_AUTHORIZED_NOT_EXECUTED' in script
    assert 'NEXT_STAGE_APPROVAL_INCLUDED=false' in script


def test_original_composite_is_explicitly_not_our_single_step_launcher():
    original = ORIGINAL.read_text()
    assert 'sudo /usr/bin/python3 -I "$TRUSTED_HELPER" --execute' in original
    assert SOURCE != ORIGINAL


def test_bash_syntax_and_invalid_options_fail_closed():
    good = subprocess.run(["bash", "-n", str(SOURCE)], capture_output=True)
    assert good.returncode == 0
    for option in ("", "--authorize", "--shell", "../execute"):
        rejected = subprocess.run(
            ["bash", str(SOURCE), option], capture_output=True, text=True,
        )
        assert rejected.returncode == 2
        assert "DENIED" in rejected.stderr


def test_copy_has_exact_protected_source_and_release_bindings():
    script = SOURCE.read_text()
    assert 'ROOT_SHA="3790bf79d4a302fe572055c3936ba28b8935ea9e1dc1a833b6b8acc9ed62878b"' in script
    assert 'PLAN_SHA="25e68eaee841791b5b857d59eef543691225ff9ea7d38fc9477eff69957e4564"' in script
    assert 'SOURCE_SHA="7b42ce983896711525de4c7955bf9fc43ac003d0"' in script
    assert 'LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"' in script
    assert 'FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"' in script
    assert 'HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"' in script
