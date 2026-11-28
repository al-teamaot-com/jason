"""Runtime-only import acceptance: V5 cannot depend on MCP/host modules."""
from datetime import datetime, timezone
from pathlib import Path
import pytest

from jason_runtime.browser_release_approval_bridge import V5BrowserApprovalDecisionBridge


class NoWrite:
    def __init__(self):self.calls=[]
    def __getattr__(self,name):
        def do(*args,**kwargs):
            self.calls.append(name)
            raise AssertionError("inactive bridge must not call "+name)
        return do


def test_runtime_only_v5_bridge_import_and_disabled_default(tmp_path):
    source=NoWrite()
    bridge=V5BrowserApprovalDecisionBridge(
        approvals=source,requests=source,signed_evidence=source,
        reviewed_route=object(),root_trust_path=tmp_path/"unavailable",
        reviewed_policy_sha256="0"*64,organization_id="test-only",
        owner_identity_ids=("owner-fixture",),
    )
    with pytest.raises(PermissionError,match="V5_BROWSER_POLICY_NOT_INSTALLED"):
        bridge.handle_signed_browser_decision(
            envelope={},exact_release=object(),now=datetime.now(timezone.utc),
        )
    assert source.calls == []


def test_even_v5_string_cannot_use_missing_governed_host_attestor(tmp_path):
    source=NoWrite()
    bridge=V5BrowserApprovalDecisionBridge(
        approvals=source,requests=source,signed_evidence=source,
        reviewed_route=object(),root_trust_path=tmp_path/"unavailable",
        reviewed_policy_sha256="0"*64,organization_id="test-only",
        owner_identity_ids=("owner-fixture",),policy_version="5.0",
    )
    with pytest.raises(PermissionError,match="HOST_ATTESTOR_NOT_INSTALLED"):
        bridge.handle_signed_browser_decision(
            envelope={},exact_release=object(),now=datetime.now(timezone.utc),
        )
    assert source.calls==[]
