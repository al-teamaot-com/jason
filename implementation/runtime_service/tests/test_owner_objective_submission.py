"""The local issuer accepts a registered task request, never an approval."""
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest
from jason_runtime.owner_objective_submission import dispatch, start_issuer
from tools.submit_owner_objective import request


class Application:
    def __init__(self):
        self.calls = []
    def submit_registered(self, **arguments):
        self.calls.append(arguments)
        return {"state": "awaiting_approval", **arguments}
    def submission_status(self, **arguments):
        return {"state": "awaiting_approval", **arguments}


@pytest.mark.parametrize("uid,message", [
    (0, {"operation":"submit","template_id":"documentation-publisher","request_id":"2"*32}),
    (1001, {"operation":"status","request_id":"2"*32}),
    (1000, {"operation":"approve","request_id":"2"*32}),
    (1000, {"operation":"submit","template_id":"documentation-publisher","request_id":"2"*32,
            "principal_id":"owner"}),
    (1000, {"operation":"submit","template_id":"documentation-publisher","request_id":"2"*32,
            "arguments":{"command":"arbitrary"}}),
])
def test_local_workload_identity_and_exact_message_shape_required(uid,message):
    app=Application()
    with pytest.raises(PermissionError):dispatch(app,message,peer_uid=uid)
    assert app.calls==[]


def test_local_submission_never_implies_an_owner_decision():
    app=Application()
    result=dispatch(app,{"operation":"submit","template_id":"documentation-publisher",
        "request_id":"2"*32},peer_uid=1000)
    assert result["state"]=="awaiting_approval"
    assert app.calls==[{"template_id":"documentation-publisher","request_id":"2"*32}]


@pytest.mark.skipif(os.geteuid()!=1000,reason="real SO_PEERCRED workload identity test requires UID1000")
def test_real_unix_socket_reuses_installed_request_and_preserves_active_listener(tmp_path):
    app=Application()
    state=tmp_path/"state";state.mkdir(mode=0o700)
    path=state/"issuer.sock"
    server=start_issuer(app,path)
    try:
        result=request({"operation":"submit","template_id":"documentation-publisher",
            "request_id":"2"*32},path=path)
        assert result["state"]=="awaiting_approval" and len(app.calls)==1
        with pytest.raises(PermissionError,match="ALREADY_RUNNING"):start_issuer(app,path)
        assert request({"operation":"status","request_id":"2"*32},path=path)["state"]=="awaiting_approval"
    finally:
        server.shutdown();server.server_close();path.unlink()


def test_non_socket_path_is_never_removed(tmp_path,monkeypatch):
    state=tmp_path/"state";state.mkdir(mode=0o700)
    path=state/"issuer.sock";path.write_text("unrelated file")
    monkeypatch.setattr(os,"geteuid",lambda:1000)
    # Host UID may differ in a disposable UID0 test. Either directory or path
    # identity must fail closed, and neither may be deleted.
    with pytest.raises(PermissionError):start_issuer(Application(),path)
    assert path.read_text()=="unrelated file"
