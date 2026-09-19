import json,pytest
from orchestrator.communication_template_design import CommunicationTemplateDesigner

class C:
 def __init__(self,r): self.r=r; self.calls=[]
 def complete(self,**kw): self.calls.append(kw); return self.r

def result(**x):
 d={"proposed_name":"Ticket – Disk Space – User Action Required","subject":"Action required: disk space on your computer","title":"Disk Space Action Required","intro":"We identified that your computer is running low on available disk space.","paragraphs":["To continue troubleshooting safely, we need your help reviewing files you no longer need."],"bullets":["Please remove or move personal files you no longer need."],"closing":"If you have questions, reply to this message and our team will assist.","required_variables":["device_name"],"rationale":"Reusable end-user wording for confirmed disk pressure."}; d.update(x); return d

def test_design_uses_structured_slots_not_html_tools():
 c=C(result()); d=CommunicationTemplateDesigner(c).design(purpose_key='disk-space-user-action',audience='end_user',scenario='confirmed disk threshold'); assert d.subject.startswith('Action required'); assert 'tools' not in c.calls[0]; payload=json.loads(c.calls[0]['user']); assert payload['audience']=='end_user'

def test_duplicate_variables_fail_closed():
 with pytest.raises(ValueError,match='unique'):
  CommunicationTemplateDesigner(C(result(required_variables=['device_name','device_name']))).design(purpose_key='x',audience='end_user',scenario='y')
