"""Optional preproduction acceptance against a REAL bundled OpenClaw Workboard card.

No Gateway start, no channel binding, no provider/API, no routing or plugin
installation. Reads a separate, previously created isolated state via a
network-disabled OpenClaw CLI container. Skips in CI without that state.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import pmv3_work_engine as engine
from pmv4_workboard_reconciliation import reconciled_card


class NativeSchemaAcceptance(unittest.TestCase):
    def test_native_card_reuses_existing_engine_after_actual_python_process_crash(self):
        loc=os.environ.get("JASON_PMV4_NATIVE_WORKBOARD_OFFLINE_STATE")
        if not loc:
            self.skipTest("Native card integration requires isolated Workboard state")
        state_dir=Path(loc).resolve(strict=True)
        self.assertIn("workboard-native-offline-state",str(state_dir))
        cmd=["docker","run","--rm","--network","none","--user","1000:1000",
             "--entrypoint","openclaw","-v",f"{state_dir}:/home/node/.openclaw",
             "openclaw:local","workboard","list","--json"]
        native=json.loads(subprocess.run(cmd,capture_output=True,text=True,check=True,timeout=40).stdout)
        self.assertEqual(len(native["cards"]),1)
        card=native["cards"][0]
        self.assertEqual(card["agentId"],"j-dev")
        work_id="PMV4-WB-"+hashlib.sha256(card["id"].encode()).hexdigest()[:16].upper()
        # The test injects the native card UUID into the EXISTING PMV3 work
        # engine, using separate Python processes and disposable storage.
        script=r"""
import sys
from pathlib import Path
import pmv3_work_engine as m
stage,item_id,path,marker=sys.argv[1:]
p=Path(path);written=Path(marker)
if stage=="init":
 s=m.empty_state()
 m.admit(s,m.make_item(item_id,"source_only_jdev_review",idempotent=True))
 m.atomic_write(p,s)
else:
 s=m.load_state(p)
 def handler(item,key):
  if stage=="crash":
   raise RuntimeError("deliberate child-process crash before any provider effect")
  with written.open("a") as h: h.write(key+"\n")
  return m.Outcome("complete",receipt="offline-test-only")
 m.execute_cycle(s,facts={},handler=handler,checkpoint=lambda state:m.atomic_write(p,state))
 m.atomic_write(p,s)
"""
        with tempfile.TemporaryDirectory(prefix="pmv4-native-recovery-") as td:
            state_path=Path(td)/"state.json"
            marker=Path(td)/"calls.log"
            env={**os.environ,"PYTHONPATH":str(ROOT/"tools")}
            def stage(label,success=True):
                result=subprocess.run([sys.executable,"-c",script,label,work_id,
                                       str(state_path),str(marker)],
                                      capture_output=True,text=True,env=env,timeout=12)
                self.assertEqual(result.returncode == 0,success,result.stderr)
            stage("init")
            stage("crash",success=False)
            self.assertFalse(marker.exists())
            self.assertEqual(engine.load_state(state_path)["items"][work_id]["phase"],"running")
            stage("recover")
            recovered=engine.load_state(state_path)
            self.assertEqual(recovered["items"][work_id]["phase"],"complete")
            self.assertEqual(len(marker.read_text().splitlines()),1)
            stage("repeat")
            self.assertEqual(len(marker.read_text().splitlines()),1)
            result=reconciled_card(card,engine.load_state(state_path))
            self.assertEqual(result["disposition"],"RECONCILE")
            self.assertFalse(result["operational_completion_verified"])

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
