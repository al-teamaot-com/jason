import json
from pathlib import Path
from communication_templates import FileCommunicationTemplateCatalog,FileCommunicationTemplateRequestStore,CommunicationTemplateService,render_aot_html

def test_aot_renderer_uses_approved_shell_and_escapes_content():
    h=render_aot_html(title='Action Required',intro='Hello <Al>',paragraphs=['Test & verify'],bullets=['One'])
    assert 'max-width:630px' in h and 'Tahoma' in h and '#e5e5e5' in h and 'width="150"' in h
    assert '*** Please enter replies above this line ***' in h
    assert 'Hello &lt;Al&gt;' in h and 'Test &amp; verify' in h

def test_approved_catalog_wins_over_request(tmp_path: Path):
    cat=tmp_path/'catalog.json'; cat.write_text(json.dumps({'templates':[{'template_id':'a','name':'Approved','purpose_key':'disk-space-user-contact','audience':'end_user','subject':'S','html_body':'H','approved':True,'source':'AOT'}]}))
    svc=CommunicationTemplateService(FileCommunicationTemplateCatalog(cat),FileCommunicationTemplateRequestStore(tmp_path/'req'))
    template,req,created=svc.find_or_request(purpose_key='disk-space-user-contact',audience='end_user',scenario='x',reason_no_fit='none',proposed_name='x',proposed_subject='x',proposed_html_body='x')
    assert template.name=='Approved' and req is None and created is False

def test_missing_template_creates_then_strengthens_request(tmp_path: Path):
    svc=CommunicationTemplateService(FileCommunicationTemplateCatalog(tmp_path/'none.json'),FileCommunicationTemplateRequestStore(tmp_path/'req'))
    html=render_aot_html(title='Disk Space',intro='We need your help.')
    _,r1,created=svc.find_or_request(purpose_key='disk-space-user-contact',audience='end_user',scenario='disk > 90%',reason_no_fit='No approved template',proposed_name='Ticket | Disk Space | User Action Required',proposed_subject='Action required: disk space on your computer',proposed_html_body=html,playbook_id='disk_space_alert',run_id='r1',ticket_id='T1')
    assert created and r1.occurrence_count==1
    _,r2,created=svc.find_or_request(purpose_key='disk-space-user-contact',audience='end_user',scenario='again',reason_no_fit='No approved template',proposed_name='ignored',proposed_subject='ignored',proposed_html_body='ignored',playbook_id='disk_space_alert',run_id='r2',ticket_id='T2')
    assert not created and r2.occurrence_count==2 and r2.source_run_ids==['r1','r2']
