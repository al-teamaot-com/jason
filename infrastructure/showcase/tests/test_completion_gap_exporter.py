import importlib.util,json
from pathlib import Path

def load():
 p=Path(__file__).resolve().parents[1]/'completion_gap_exporter.py'; s=importlib.util.spec_from_file_location('cg',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def test_metrics_hide_ticket_run_evidence_and_summary(tmp_path):
 m=load(); m.ROOT=tmp_path; (tmp_path/'g.json').write_text(json.dumps({'gap_id':'GAP-x','problem_key':'provider:x','gap_class':'provider_capability','title':'Missing API capability','summary':'SECRET SUMMARY','route_target':'capability_backlog','lifecycle':'routed','occurrence_count':3,'run_ids':['RUNSECRET'],'ticket_ids':['TSECRET'],'evidence_refs':['EVSECRET']})); metrics=m.render_metrics(); assert 'jason_completion_gaps_active 1' in metrics; assert 'jason_completion_gap_occurrences{gap_id="GAP-x"} 3' in metrics; assert 'route_target="capability_backlog"' in metrics
 for secret in ('RUNSECRET','TSECRET','EVSECRET','SECRET SUMMARY'): assert secret not in metrics
