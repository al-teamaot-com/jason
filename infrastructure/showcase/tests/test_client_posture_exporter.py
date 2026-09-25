import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import client_posture_exporter as e

def test_posture_metrics_are_aggregate_and_hide_client_identity(tmp_path):
 d={"reviewed_at":"2026-09-25T07:20:00Z","client":{"autotask_company_id":"333","name":"Secret Client"},"assessments":[{"state":"confirmed_gap"},{"state":"unknown"},{"state":"evidence_unavailable"}]}
 (tmp_path/'333.json').write_text(json.dumps(d)); m=e.metrics(tmp_path)
 assert 'jason_client_posture_reviews 1' in m and 'state="confirmed_gap"} 1' in m
 assert 'Secret Client' not in m and '333' not in m
