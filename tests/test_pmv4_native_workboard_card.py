"""Optional preproduction acceptance against a REAL bundled OpenClaw Workboard card.

No Gateway start, no channel binding, no provider/API, no routing or plugin
installation. Reads a separate, previously created isolated state via a
network-disabled OpenClaw CLI container. Skips in CI without that state.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import pmv3_work_engine as engine
from pmv4_workboard_reconciliation import reconciled_card


class NativeSchemaAcceptance(unittest.TestCase):
    def test_existing_bundled_workboard_card_is_conservatively_reconciled(self):
        loc=os.environ.get("JASON_PMV4_NATIVE_WORKBOARD_OFFLINE_STATE")
        if not loc:
            self.skipTest("No isolated OpenClaw Workboard state set (CI is source-only)")
        state_dir=Path(loc).resolve(strict=True)
        self.assertNotEqual(state_dir, Path("/opt/jason/services/openclaw/data/config"))
        self.assertTrue("workboard-native-offline-state" in str(state_dir))
        cmd=[
            "docker","run","--rm","--network","none","--user","1000:1000",
            "--entrypoint","openclaw",
            "-v",f"{state_dir}:/home/node/.openclaw",
            "openclaw:local","workboard","list","--json",
        ]
        output=subprocess.run(cmd,capture_output=True,text=True,check=True,timeout=40)
        records=json.loads(output.stdout)
        cards=records["cards"]
        self.assertEqual(len(cards),1)
        card=cards[0]
        self.assertEqual(card["status"],"ready")
        self.assertEqual(card["agentId"],"j-dev")
        work_id="PMV4-WB-"+hashlib.sha256(card["id"].encode()).hexdigest()[:16].upper()
        state=engine.empty_state()
        engine.admit(state,engine.make_item(work_id,"offline_review",idempotent=True))
        result=reconciled_card(card,state)
        self.assertEqual(result["work_item_id"],work_id)
        self.assertEqual(result["disposition"],"IN_PROGRESS")
        self.assertFalse(result["eligible_for_automated_retry"])
        self.assertFalse(result["operational_completion_verified"])
        state["items"][work_id]["phase"]="complete"
        key=engine.action_key(work_id,"offline_review",1)
        state["receipts"][key]={"item_id":work_id,"receipt":"offline-only-evidence"}
        result=reconciled_card(card,state)
        self.assertEqual(result["disposition"],"RECONCILE")
        # Even cross-linked, source-only test must never claim real completion.
        self.assertFalse(result["operational_completion_verified"])


if __name__=="__main__":
    unittest.main()
