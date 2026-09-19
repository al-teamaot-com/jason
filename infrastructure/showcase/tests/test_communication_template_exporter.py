import importlib.util,json,os
from pathlib import Path

def load():
 p=Path(__file__).resolve().parents[1]/'communication_template_exporter.py'; s=importlib.util.spec_from_file_location('ct',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def test_metrics_hide_html_and_ticket_run_context(tmp_path,monkeypatch):
 cat=tmp_path/'cat.json'; req=tmp_path/'req'; req.mkdir(); cat.write_text(json.dumps({'templates':[{'approved':True,'audience':'end_user','html_body':'SECRETHTML'}]})); (req/'x.json').write_text(json.dumps({'request_id':'CTR-x','purpose_key':'x','audience':'end_user','lifecycle':'drafted','proposed_name':'Proposed','proposed_subject':'Subject','proposed_html_body':'SECRETHTML2','source_ticket_ids':['TSECRET'],'source_run_ids':['RUNSECRET'],'occurrence_count':2}))
 m=load(); m.CATALOG=cat; m.REQUESTS=req; metrics=m.render_metrics(); assert 'jason_communication_templates_approved 1' in metrics; assert 'jason_communication_template_active_requests 1' in metrics; assert 'proposed_name="Proposed"' in metrics; assert 'SECRETHTML' not in metrics and 'TSECRET' not in metrics and 'RUNSECRET' not in metrics
