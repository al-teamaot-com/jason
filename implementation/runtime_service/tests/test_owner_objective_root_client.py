"""Atomic typed transport in disposable directories; no production connections."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
import time

import pytest
from jason_runtime.owner_objective_root_client import ObjectiveRootClient,ObjectiveRootRequestDenied
from tools.owner_objective_root_worker import put_at


@pytest.fixture
def client(tmp_path):
    for name,mode in (("requests",0o700),("staging",0o700),("results",0o755)):
        (tmp_path/name).mkdir(mode=mode)
    return ObjectiveRootClient(tmp_path,timeout_seconds=2,expected_root_uid=os.geteuid())


def respond(client, *, denied=False):
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        rows=list((client.spool/"requests").iterdir())
        if rows:
            path=rows[0]
            raw=path.read_bytes()
            assert path.name==sha256(raw).hexdigest()+".json"
            request=json.loads(raw)
            assert request["operation"]=="status"
            record={"request_id":path.stem,"status":"succeeded","result":{"state":"verified_complete"}}
            if denied:record.update(status="denied",reason_code="TEST_DENIED",execution_state="not_started")
            fd=os.open(client.spool/"results",os.O_RDONLY|os.O_DIRECTORY)
            try:put_at(fd,path.name,json.dumps(record).encode(),0o444)
            finally:os.close(fd)
            return request
        time.sleep(.005)
    raise AssertionError("no complete request published")


def test_only_complete_hashed_request_and_complete_root_result_are_visible(client):
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker=pool.submit(respond,client)
        assert client.call("status",approval_id="planapproval-objective-"+"1"*32)["state"]=="verified_complete"
        assert len(worker.result()["observation_id"])==32
    assert not list((client.spool/"staging").iterdir())


def test_typed_root_denial_preserves_unknown_versus_not_started(client):
    with ThreadPoolExecutor(max_workers=1) as pool:
        worker=pool.submit(respond,client,denied=True)
        with pytest.raises(ObjectiveRootRequestDenied) as caught:
            client.call("status",approval_id="planapproval-objective-"+"1"*32)
        assert caught.value.execution_state=="not_started"
        worker.result()


def test_unregistered_root_operation_cannot_enter_queue(client):
    with pytest.raises(PermissionError):client.call("shell",command="anything")
    assert not list((client.spool/"requests").iterdir())
