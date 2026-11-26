from pathlib import Path
import pytest
from tools import audit_journal_reader_release_packet as packet

SOURCE=Path(__file__).resolve().parents[2]


def data():
    a={packet.READING_SOURCE:(SOURCE/packet.READING_SOURCE).read_bytes(),
       packet.ROOT_SOURCE:(SOURCE/packet.ROOT_SOURCE).read_bytes()}
    return dict(candidate="e"*40,rollback_main="d"*40,source_blobs=a,
        prior_images={name:"sha256:"+format(i,"064x") for i,name in enumerate(packet.READERS,1)},
        prior_source_digests={name:format(i+10,"064x") for i,name in enumerate(a)},
        desired_policy_sha256="a"*64,freeze_sha256="b"*64,archive_sha256="c"*64,
        protected_peer_ids={name:format(i+20,"064x") for i,name in enumerate(packet.READERS,1)})


def test_reviewer_receipt_binds_only_three_current_consumers_two_readers():
    result=packet.bind_scope(**data())
    assert packet.verify_packet(result)
    assert len(result["scope"]["exact_consumers"])==3
    assert result["scope"]["automatic_acceptance_gates"][-1]=="same_global_freeze_state_and_root_journal_policy"
    assert result["scope"]["owner_signature_claimed"] is False
    assert result["scope"]["root_installation_performed"] is False


@pytest.mark.parametrize("field,value",[
    ("candidate","notsha"),
    ("rollback_main","e"*40),
    ("desired_policy_sha256","bad"),
    ("prior_images",{"jason-runtime":"sha256:"+"0"*64}),
    ("protected_peer_ids",{}),
])
def test_invalid_source_or_rollback_proof_denied(field,value):
    src=data();src[field]=value
    with pytest.raises(ValueError,match="AUDIT_READER_RELEASE_"):
        packet.bind_scope(**src)


def test_old_open_reader_cannot_get_release_scope():
    src=data();src["source_blobs"][packet.READING_SOURCE]=b"old code without connection closing"
    with pytest.raises(ValueError,match="CLOSED_READERS_REQUIRED"):
        packet.bind_scope(**src)


def test_packet_cannot_grant_itself_approval_or_enlarge_scope():
    res=packet.bind_scope(**data())
    res["scope"]["owner_signature_claimed"]=True
    with pytest.raises(ValueError,match="SCOPE_HASH_TAMPERED"):
        packet.verify_packet(res)
    res=packet.bind_scope(**data())
    res["scope"]["out_of_scope"].remove("no_historical_record_deletion")
    res["scope_sha256"]=packet.sha256(packet.canon(res["scope"])).hexdigest()
    with pytest.raises(ValueError,match="RELEASE_SCOPE_CHANGE"):
        packet.verify_packet(res)
