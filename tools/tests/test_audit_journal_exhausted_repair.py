"""Consumed prior Root retry is lineage evidence only, never authority to replay."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import audit_journal_pre_cutover_repair as repair


def fixture(monkeypatch, *, contents=None, claimed=None):
    claimed=claimed or datetime.now(timezone.utc)-timedelta(minutes=6)
    row={"claimed_at":claimed.isoformat()}
    retry=contents if contents is not None else {
        "scope_sha256":repair.EXHAUSTED_CONTEXT_SCOPE,
        "observed_at":(claimed+timedelta(minutes=2)).isoformat()}
    raw=repair.canon(retry)
    seen=[]
    def read(path,mode):
        seen.append((path,mode))
        assert path==Path("/fixture/previous/retry.json") and mode==0o400
        return raw
    monkeypatch.setattr(repair,"raw_file",read)
    return row,raw,seen


def test_exhausted_retry_attests_existing_immutable_marker(monkeypatch):
    row,raw,seen=fixture(monkeypatch)
    assert repair.exhausted_retry_proof(Path("/fixture/previous"),row,repair.EXHAUSTED_CONTEXT_SCOPE)==repair.digest(raw)
    assert len(seen)==1


@pytest.mark.parametrize("change",["wrong_scope","missing_scope","extra_key","non_object",
                                    "before_claim","after_budget","naive_time","invalid_time"])
def test_consumed_retry_denies_untrusted_or_replayed_evidence(monkeypatch,change):
    claimed=datetime.now(timezone.utc)-timedelta(minutes=10)
    marker={"scope_sha256":repair.EXHAUSTED_CONTEXT_SCOPE,
            "observed_at":(claimed+timedelta(minutes=2)).isoformat()}
    if change=="wrong_scope":marker["scope_sha256"]="f"*64
    elif change=="missing_scope":marker.pop("scope_sha256")
    elif change=="extra_key":marker["arbitrary_authorization"]=True
    elif change=="non_object":marker=[]
    elif change=="before_claim":marker["observed_at"]=(claimed-timedelta(seconds=1)).isoformat()
    elif change=="after_budget":marker["observed_at"]=(claimed+timedelta(seconds=28801)).isoformat()
    elif change=="naive_time":marker["observed_at"]=claimed.replace(tzinfo=None).isoformat()
    elif change=="invalid_time":marker["observed_at"]="nonsense"
    row,_,_=fixture(monkeypatch,contents=marker,claimed=claimed)
    with pytest.raises((PermissionError,ValueError,TypeError,KeyError)):
        repair.exhausted_retry_proof(Path("/fixture/previous"),row,repair.EXHAUSTED_CONTEXT_SCOPE)


def test_existing_one_use_paths_stay_distinct():
    assert repair.EXHAUSTED_CONTEXT_CANDIDATE!=repair.FAILED_CONTEXT_CANDIDATE
    assert repair.EXHAUSTED_CONTEXT_SCOPE!=repair.FAILED_CONTEXT_SCOPE
    assert repair.EXHAUSTED_CONTEXT_CANDIDATE!=repair.OLD
    assert repair.EXHAUSTED_CONTEXT_SCOPE!=repair.OLD_SCOPE


def test_new_scope_requires_exhausted_previous_receipt():
    from inspect import getsource
    src=getsource(repair.preflight)
    assert "EXHAUSTED_CONTEXT_RECORD_REQUIRED" in src
    assert "exhausted=True,predecessor=prior_context" in src
