import json,pytest
from orchestrator.component_engineering_design import ComponentEngineeringDesigner

class Client:
 def __init__(self,result): self.result=result; self.calls=[]
 def complete(self,**kwargs): self.calls.append(kwargs); return self.result

def base(**x):
 d={"recommendation":"improve_existing","rationale":"Existing component is closest fit but lacks bounded structured output.","proposed_name":"Get Disk Usage Detail AOT Ver NEXT","purpose":"Return actionable disk growth evidence.","inputs":["Drive letter"],"result_fields":["status","used_pct","free_gb","largest_folders"],"safety_class":"read_only","implementation_requirements":["No file deletion","Emit JASON_RESULT block"],"test_plan":["Static parse test","Run on approved test device"],"acceptance_criteria":["Returns bounded structured data"],"promotion_requires_human_approval":False}; d.update(x); return d

def test_design_is_bounded_and_reuses_supplied_context():
 c=Client(base()); r=ComponentEngineeringDesigner(c).design(request={"request_id":"CER-1","gap":"x"},existing_components=[{"name":"Existing"}],native_capabilities=[],evidence_summaries=[{"summary":"gap"}]); assert r.recommendation=='improve_existing'; payload=json.loads(c.calls[0]['user']); assert payload['existing_components'][0]['name']=='Existing'; assert 'tools' not in c.calls[0]

def test_modifying_or_disruptive_must_require_promotion_approval():
 for safety in ('modifying','disruptive'):
  with pytest.raises(ValueError,match='require promotion approval'): ComponentEngineeringDesigner(Client(base(safety_class=safety,promotion_requires_human_approval=False))).design(request={"request_id":"CER-1"},existing_components=[],native_capabilities=[],evidence_summaries=[])
