from datetime import datetime, timezone
import pytest
from decision_memory.resolution_ingestion import ConfirmedResolutionIngestion, ResolutionIngestionError
from decision_memory.resolution_memory import ResolutionCaseStatus, ResolutionOutcome, ResolutionSignature, ResolutionSourceReference

NOW=datetime(2026,9,18,tzinfo=timezone.utc)
def candidate(**overrides):
    data=dict(case_id='AT-T1',organization_id='aot',client_id='company:311',ticket_id='T1',ticket_company_id='311',current_company_id='311',signature=ResolutionSignature(category='browser policy',product='Chrome Edge',device_role='workstation',platform='Windows',symptoms=('managed by organization',)),source_references=(ResolutionSourceReference(source_type='autotask_ticket',source_id='T1',correlation_id='corr-1'),),steps=(),root_cause='Machine policy present',final_resolution='Confirmed policy source',outcome=ResolutionOutcome.RESOLVED,technician_confirmed=True,terminal_verification_confirmed=True,recorded_at=NOW,resolved_at=NOW,owner='person-al')
    data.update(overrides); return ConfirmedResolutionIngestion(**data)
def test_verified_requires_exact_company_and_terminal_evidence():
    assert candidate().to_case().status is ResolutionCaseStatus.VERIFIED
    with pytest.raises(ResolutionIngestionError,match='company boundary'): candidate(current_company_id='250').to_case()
    with pytest.raises(ResolutionIngestionError,match='terminal verification'): candidate(terminal_verification_confirmed=False).to_case()
def test_unconfirmed_nonresolved_history_is_observed_not_verified():
    case=candidate(outcome=ResolutionOutcome.IMPROVED,technician_confirmed=False,terminal_verification_confirmed=False).to_case()
    assert case.status is ResolutionCaseStatus.OBSERVED

def test_service_ingests_confirmed_case_durably(tmp_path):
    from decision_memory.resolution_service import ResolutionMemoryService
    from decision_memory.resolution_sqlite import SQLiteResolutionMemoryStore
    store=SQLiteResolutionMemoryStore(str(tmp_path/'r.sqlite3')); service=ResolutionMemoryService(store=store); service.initialize()
    case=service.ingest_confirmed_resolution(candidate())
    assert case.status is ResolutionCaseStatus.VERIFIED
    assert store.count_cases(organization_id='aot',client_id='company:311') == 1
