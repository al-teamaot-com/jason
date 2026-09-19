import json,pytest
from orchestrator.component_engineering_design import ComponentEngineeringDesigner

class Client:
 def __init__(self,result): self.result=result; self.calls=[]
 def complete(self,**kwargs): self.calls.append(kwargs); return self.result

def base(**x):
 d={"recommendation":"improve_existing","rationale":"Existing component is closest fit but lacks bounded structured output.","proposed_name":"Get Disk Usage Detail AOT Ver NEXT","purpose":"Return actionable disk growth evidence.","inputs":["Drive letter"],"result_fields":["status","used_pct","free_gb","largest_folders"],"safety_class":"read_only","implementation_requirements":["No file deletion","Emit JASON_RESULT block"],"test_plan":["Static parse test","Run on approved test device"],"acceptance_criteria":["Returns bounded structured data"],"promotion_requires_human_approval":False}; d.update(x); return d

def test_design_is_bounded_and_reuses_supplied_context():
 c=Client(base()); r=ComponentEngineeringDesigner(c).design(request={"request_id":"CER-1","gap":"x"},existing_components=[{"name":"Existing","satisfies_request":True}],native_capabilities=[],evidence_summaries=[{"summary":"gap"}]); assert r.recommendation=='improve_existing'; payload=json.loads(c.calls[0]['user']); assert payload['existing_components'][0]['name']=='Existing'; assert 'tools' not in c.calls[0]

def test_modifying_or_disruptive_must_require_promotion_approval():
 for safety in ('modifying','disruptive'):
  with pytest.raises(ValueError,match='require promotion approval'): ComponentEngineeringDesigner(Client(base(safety_class=safety,promotion_requires_human_approval=False))).design(request={"request_id":"CER-1"},existing_components=[],native_capabilities=[],evidence_summaries=[])


def test_design_client_falls_back_when_primary_transport_fails():
 from orchestrator.component_engineering_design import FallbackStructuredDesignClient
 class Primary:
  def complete(self,**kwargs): raise RuntimeError('429')
 fallback=Client(base())
 client=FallbackStructuredDesignClient(Primary(),fallback)
 result=client.complete(system='s',user='u',schema={})
 assert result['recommendation']=='improve_existing' and len(fallback.calls)==1


def test_reuse_recommendations_require_explicitly_sufficient_supplied_option():
 with pytest.raises(ValueError,match='explicitly sufficient existing'):
  ComponentEngineeringDesigner(Client(base(recommendation='use_existing'))).design(request={'request_id':'CER-1'},existing_components=[{'name':'Problematic','satisfies_request':False}],native_capabilities=[],evidence_summaries=[])
 with pytest.raises(ValueError,match='explicitly sufficient native'):
  ComponentEngineeringDesigner(Client(base(recommendation='prefer_native_capability'))).design(request={'request_id':'CER-1'},existing_components=[],native_capabilities=[{'capability':'x','satisfies_request':False}],evidence_summaries=[])
