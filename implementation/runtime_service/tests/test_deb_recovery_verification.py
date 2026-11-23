from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest

from jason_runtime.deb_recovery_verification import (
    DebRecoveryEvidenceError, backupiq_read_arguments, verify_deb_recovery,
)

NOW = datetime(2026, 11, 23, 13, tzinfo=timezone.utc)
BASELINE = NOW - timedelta(minutes=30)


def receipt(capability, items):
    return {"status": "succeeded", "capability": capability,
            "correlation_id": "synthetic-receipt", "evidence": {
                "provider": "backup_net", "data": {"items": items}, "warnings": []}}


def inputs():
    args = backupiq_read_arguments(company_id=0, hostname="SYNTH-1", asset_id="asset-1")
    return dict(company_id=0, hostname="SYNTH-1", asset_id="asset-1",
                expected_customer_id="synthetic-bound-customer",
                asset_read_arguments=args["asset_read"], alert_read_arguments=args["alerts"],
                asset_receipt=receipt("backup.endpoint.asset.read", [{
                    "id": "asset-1", "name": "SYNTH-1", "status": "online",
                    "customerId": "synthetic-bound-customer", "backupEnabled": True,
                    "lastSuccessfulBackupTimestamp": (NOW-timedelta(minutes=1)).isoformat()}]),
                alert_receipt=receipt("backup.backupiq.alert.search", []),
                remediation_baseline=BASELINE, observed_at=NOW,
                deadline=BASELINE+timedelta(hours=3))


def test_all_selectors_retain_company_including_aot_zero():
    assert all(a["company_id"] == "0" for a in backupiq_read_arguments(
        company_id=0, hostname="SYNTH-1", asset_id="asset-1").values())


@pytest.mark.parametrize("company", [None, True, False, -1, "unknown", "", "0.1"])
def test_missing_or_ambiguous_company_is_not_a_provider_credential_error(company):
    with pytest.raises(DebRecoveryEvidenceError, match="EXACT_COMPANY"):
        backupiq_read_arguments(company_id=company, hostname="SYNTH-1", asset_id="asset-1")


def test_fresh_exact_online_enabled_asset_and_clear_alert_verify_provider_only():
    result = verify_deb_recovery(**inputs())
    assert result.fresh_backup_verified
    assert result.disposition == "provider_recovery_verified"
    assert not result.provider_mutation_allowed
    assert result.next_recheck_at is None


@pytest.mark.parametrize("timestamp", [(BASELINE-timedelta(seconds=1)).isoformat(),
                                      BASELINE.isoformat(), None])
def test_old_missing_or_equal_baseline_success_cannot_close(timestamp):
    a = inputs(); a['asset_receipt']['evidence']['data']['items'][0]['lastSuccessfulBackupTimestamp']=timestamp
    result = verify_deb_recovery(**a)
    assert result.disposition == "waiting_backup"
    assert not result.fresh_backup_verified
    assert result.next_recheck_at == NOW + timedelta(minutes=15)


@pytest.mark.parametrize("status", ["inprogress", "running"])
def test_active_backup_is_waiting_and_never_declared_recovered_or_offline(status):
    a = inputs(); a['asset_receipt']['evidence']['data']['items'][0]['status']=status
    result=verify_deb_recovery(**a)
    assert result.disposition=='waiting_backup'
    assert not result.fresh_backup_verified and not result.provider_mutation_allowed


def test_current_alert_prevents_completion_even_after_fresh_success():
    a=inputs();a['alert_receipt']['evidence']['data']['items']=[{'id':'active-alert'}]
    assert not verify_deb_recovery(**a).fresh_backup_verified


def test_deadline_survives_restart_and_progress_cannot_extend_it():
    a=inputs(); a['remediation_baseline']=NOW-timedelta(hours=3);a['deadline']=NOW
    a['asset_receipt']['evidence']['data']['items'][0]['status']='inprogress'
    assert verify_deb_recovery(**a).disposition=='verification_deadline_human_review'


@pytest.mark.parametrize('field,value', [('id','wrong'),('name','wrong'),('customerId','other-client')])
def test_wrong_asset_hostname_or_customer_rejects(field,value):
    a=inputs();a['asset_receipt']['evidence']['data']['items'][0][field]=value
    with pytest.raises(DebRecoveryEvidenceError):verify_deb_recovery(**a)


@pytest.mark.parametrize('kind', ['asset_receipt','alert_receipt'])
def test_failed_unauthorized_read_never_becomes_empty_success(kind):
    a=inputs();a[kind]={'status':'failed','error_code':'CONNECTOR_AUTHORIZATION_DENIED'}
    with pytest.raises(DebRecoveryEvidenceError,match='GOVERNED_READ_FAILED'):verify_deb_recovery(**a)


@pytest.mark.parametrize('change', ['unscoped','other-company','future','naive','too-long','warnings','wrong-capability','duplicate'])
def test_invalid_receipts_or_baselines_fail_closed(change):
    a=inputs()
    asset=a['asset_receipt']['evidence']['data']['items'][0]
    if change=='unscoped':a['asset_read_arguments'].pop('company_id')
    elif change=='other-company':a['alert_read_arguments']['company_id']='99'
    elif change=='future':asset['lastSuccessfulBackupTimestamp']=(NOW+timedelta(seconds=1)).isoformat()
    elif change=='naive':a['observed_at']=NOW.replace(tzinfo=None)
    elif change=='too-long':a['deadline']=BASELINE+timedelta(days=7)
    elif change=='warnings':a['asset_receipt']['evidence']['warnings']=['truncated']
    elif change=='wrong-capability':a['asset_receipt']['capability']='other.read'
    elif change=='duplicate':a['asset_receipt']['evidence']['data']['items'].append(deepcopy(asset))
    with pytest.raises(DebRecoveryEvidenceError):verify_deb_recovery(**a)
