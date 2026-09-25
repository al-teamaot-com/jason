import json

from .attention_scheduler import AutonomyConfig
from .autonomous_queue_worker import QueueCandidate
from .catalog_classifier import CatalogPlaybookClassifier
from .playbook_catalog import PlaybookCatalog
from .shadow_assessment import ShadowQueueAssessor


class Queue:
    def reconcile_candidates(self):
        return (
            QueueCandidate('3',10,'Jason',True,context={'title':'Known alert','configurationItemID':3}),
            QueueCandidate('1',30,'Jason',True,context={'title':'Known alert','configurationItemID':1}),
            QueueCandidate('2',20,'Help Desk I',False,context={'title':'Unknown request','configurationItemID':2}),
        )


def test_shadow_assessment_selects_two_without_mutation(tmp_path):
    path=tmp_path/'registry.json'
    path.write_text(json.dumps({
        'schema_version':2,
        'playbooks':[{
            'id':'known','name':'Known','version':'1.0','lifecycle':'production','enabled':True,'source':'x',
            'trigger':{'title_contains':['known alert']},
            'autonomy':{'activation':'shadow','policy_id':'pb:known','required_gates':['trigger','identity','autonomy_approved'],'allowed_capabilities':[]},
        }]
    }),encoding='utf-8')
    assessment=ShadowQueueAssessor(
        config=AutonomyConfig(2),
        queue_source=Queue(),
        classifier=CatalogPlaybookClassifier(PlaybookCatalog.load(path)),
    ).assess()
    assert assessment.candidate_count == 3
    assert [x.resource_id for x in assessment.selected_for_attention] == ['1','3']
    assert assessment.selected_for_attention[0].match_state == 'candidate_investigation'
    assert assessment.selected_for_attention[1].match_state == 'candidate_investigation'
    assert not any(x.standing_authority_active for x in assessment.all_items)
