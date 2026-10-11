import base64
import json
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from operational_acceptance_reader import verify_acceptance, accepted_operational_dependencies
from todo_release_bridge import dependency_state_for_item


def fixture():
    key = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    payload = {'identity':'acceptance-network-posture','state':'operationally_accepted', 'issue_number':953,
               'receipt_id':'test-receipt-001','evidence_ref':'governed:network-evidence-001',
               'issued_at':(now-timedelta(hours=1)).isoformat(),
               'expires_at':(now+timedelta(days=2)).isoformat()}
    trust = {'issuers':{'aot-owner':base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()},'revoked_receipts':[]}
    message=json.dumps({'issuer':'aot-owner','payload':payload},sort_keys=True,separators=(',', ':'),ensure_ascii=True).encode()
    receipt={'issuer':'aot-owner','payload':payload,'signature':base64.b64encode(key.sign(message)).decode()}
    return receipt,trust


def test_signed_scope_and_revocation():
    receipt,trust=fixture()
    name='acceptance-network-posture'
    assert verify_acceptance(receipt,trust,identity=name,issue_number=953)
    assert verify_acceptance(receipt,trust,identity=name,issue_number=954) is None
    assert verify_acceptance(receipt,trust,identity='acceptance-other',issue_number=953) is None
    trust['revoked_receipts']=['test-receipt-001']
    assert verify_acceptance(receipt,trust,identity=name,issue_number=953) is None


def test_tampering_expiry_and_untrusted_issuer():
    receipt,trust=fixture()
    name='acceptance-network-posture'
    receipt['payload']['evidence_ref']='issue-closed'
    assert verify_acceptance(receipt,trust,identity=name,issue_number=953) is None
    receipt,trust=fixture()
    trust['issuers']={}
    assert verify_acceptance(receipt,trust,identity=name,issue_number=953) is None
    receipt,trust=fixture()
    receipt['payload']['expires_at']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    assert verify_acceptance(receipt,trust,identity=name,issue_number=953) is None


def test_reader_and_release_gate_fail_closed(tmp_path):
    receipt,trust=fixture()
    root=tmp_path/'protected-operational-acceptance'
    (root/'receipts').mkdir(parents=True)
    (root/'trust.json').write_text(json.dumps(trust))
    (root/'receipts'/'acceptance-network-posture.json').write_text(json.dumps(receipt))
    evidence=accepted_operational_dependencies(root,['acceptance-network-posture'],953)
    assert evidence['acceptance-network-posture']['authority_verified'] is True
    item={'issue_number':953,'blocker_category':'dependency','governing_dependencies':['release-1234567890abcdef'],
          'governing_operational_dependencies':['acceptance-network-posture']}
    assert dependency_state_for_item(item,tmp_path)['retry_eligible'] is False
    assert dependency_state_for_item(item,tmp_path)['operational_eligible'] is True
    (root/'trust.json').unlink()
    assert dependency_state_for_item(item,tmp_path)['operational_eligible'] is False
