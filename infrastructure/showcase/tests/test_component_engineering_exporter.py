import importlib.util,json
from pathlib import Path


def load():
 p=Path(__file__).resolve().parents[1]/'component_engineering_exporter.py'; s=importlib.util.spec_from_file_location('cex',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def test_metrics_are_operational_and_hide_sensitive_context(tmp_path: Path):
 m=load(); rows=[
  {"request_id":"CER-disk","title":"Improve disk evidence","problem_key":"disk-space:largest-files","kind":"improve_existing","lifecycle":"open","risk":"read_only","existing_component_name":"DattoSize","owner":"Jason Architecture Authority","occurrence_count":3,"source_ticket_ids":["TSECRET"],"source_run_ids":["RUNSECRET"],"evidence_refs":["EVSECRET"],"gap_summary":"SECRET SUMMARY","proposed_change":"SECRET CODE"},
  {"request_id":"CER-old","title":"Old","problem_key":"old","kind":"new_component","lifecycle":"resolved","risk":"modifying","occurrence_count":1}
 ]
 for r in rows: (tmp_path/(r['request_id']+'.json')).write_text(json.dumps(r))
 metrics=m.render_metrics(requests_path=tmp_path)
 assert 'jason_component_engineering_requests 2' in metrics
 assert 'jason_component_engineering_active_requests 1' in metrics
 assert 'jason_component_engineering_occurrences{request_id="CER-disk"} 3' in metrics
 assert 'existing_component="DattoSize"' in metrics
 for secret in ('TSECRET','RUNSECRET','EVSECRET','SECRET SUMMARY','SECRET CODE'): assert secret not in metrics
