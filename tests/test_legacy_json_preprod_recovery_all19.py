"""19 independent, isolated per-playbook registry interruption/reopen probes.

A draft/restart probe is NOT production job interruption acceptance. No
provider reads/writes, no activation, no service/release mutation.
"""
import copy
import json
import pytest
from implementation.autonomous_remediation.playbook_store import SQLitePlaybookRegistry
from implementation.autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from tools.legacy_json_acceptance_ledger import ROOT, build

CASES = tuple(build()["entries"])


@pytest.mark.parametrize("record", CASES, ids=lambda x: x["id"])
def test_exact_candidate_draft_reopen_no_replay_or_mutation(record, tmp_path):
    source=json.loads((ROOT/record["json_source_path"]).read_text())
    p=tmp_path/"one-source-draft-recovery.sqlite3"
    before=SQLitePlaybookRegistry(p)
    try:
        item=before.stage(source, actor="isolated-draft-only")
        assert item.state=="draft"
        assert item.document.fingerprint==record["json_fingerprint"]
        assert before.generation()==1
        assert before.active_snapshot()[1]==()
    finally:
        before.close()
    # Simulate worker exit and cold reconnect to the same private journal.
    after=SQLitePlaybookRegistry(p,read_only=True)
    try:
        item=after.get(record["id"],record["json_version"])
        assert item.state=="draft"
        assert item.document.fingerprint==record["json_fingerprint"]
        assert len(after.lifecycle_events())==1
        assert after.generation()==1
        assert after.active_snapshot()[1]==()
        runner=JsonPlaybookInterpreter(item.document)
        # A complete action is not implied by a recovered JSON definition.
        for step in source["steps"]:
            if step["type"]=="remediation":
                assert step["approval_required"] is True
                try:
                    instruction=runner.instruction(step_id=step["id"],facts={})
                except KeyError as exc:
                    assert "PLAYBOOK_REQUIRED_FACT_MISSING" in str(exc)
                else:
                    assert instruction.approval_required is True
        with pytest.raises(RuntimeError,match="PLAYBOOK_READONLY_MUTATION_FORBIDDEN"):
            after.stage(source, actor="forbidden-in-read-only-restart")
    finally:
        after.close()
    # Reopened writer does not replay stage as a new release or event.
    restarted=SQLitePlaybookRegistry(p)
    try:
        restarted.stage(source, actor="isolated-draft-only")
        assert restarted.generation()==1
        assert len(restarted.lifecycle_events())==1
        changed=copy.deepcopy(source)
        changed["playbook"]["name"] += " changed and not approved"
        with pytest.raises(ValueError,match="PLAYBOOK_VERSION_IMMUTABLE"):
            restarted.stage(changed,actor="deny-historical-mutation")
        assert restarted.generation()==1
        assert restarted.active_snapshot()[1]==()
    finally:
        restarted.close()
