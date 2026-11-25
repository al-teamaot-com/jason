"""Stage E: six-unit replacement under the EXISTING signed native release engine.

Isolated provider-free test ONLY. Exact trusted Owner signature, shared host
and freeze locks, native receipt, interrupted recovery and replay denial.
No service, provider, systemd, protected root or production mutation.
"""
from __future__ import annotations

from contextlib import contextmanager
import json

import pytest

from tools import independent_component_release as native
from tools import pmv4_e_six_unit_transaction_model as units
from implementation.kernel.signed_owner_release import OwnerReleaseProofDenied
from tools.tests.test_pmv4_e_providerfree_canary import (
    NoProviderHost,packet,exact_owner_proof,CANDIDATE,canary,
)


class SixUnitNativeHost(NoProviderHost):
    def __init__(self,*,fail_step=None,fail_rollback=False):
        super().__init__()
        self.before=units.baseline()
        self.state=self.before
        self.fail_step=fail_step
        self.fail_rollback=fail_rollback
        self.release_calls=0
        self.rollback_calls=0

    def observe(self,project):
        assert project==canary.CANARY_PROJECT
        return CANDIDATE if self.state.accepted_marker else None

    def activate(self,bundle,manifest):
        assert self.calls[-1]=="freeze_locked"
        assert manifest["provider_scope"]["provider"]=="none"
        assert self.release_calls==0
        self.release_calls+=1
        # This models six exact callbacks as ONE host transaction owned
        # by the existing native controller, not six competing release engines.
        self.state,phases=units.cutover(self.before,fail_after=self.fail_step)
        assert len(phases)==7
        assert self.state.ticket_owner==self.before.ticket_owner

    def restore(self,previous,manifest):
        assert previous is None
        self.rollback_calls+=1
        if self.fail_rollback:
            raise PermissionError("SIMULATED_ROOT_ROLLBACK_NOT_VERIFIED")
        if self.state.accepted_marker:
            self.state=units.rollback(self.state,self.before)
        else:
            self.state=self.before

    def verify(self,bundle,manifest):
        if bundle is None:
            return self.state==self.before
        if self.fail_acceptance:
            return False
        return (self.state.accepted_marker
                and self.state.active_user==units.NEW_USER
                and self.state.active_root==units.NEW_ROOT
                and not (self.state.active_user & units.OLD_USER)
                and not (self.state.active_root & units.OLD_ROOT))


def test_native_signed_one_owner_six_unit_lifecycle_isolated(tmp_path):
    root,manifest=packet(tmp_path)
    host=SixUnitNativeHost()
    result=host.controller(root).promote(manifest,exact_owner_proof(manifest))
    assert result["status"]=="component_accepted"
    assert result["protected_services_changed"] is False
    assert host.state.accepted_marker is True
    assert host.state.freeze==host.before.freeze
    assert host.state.core_sha==host.before.core_sha
    assert host.state.mcp_sha==host.before.mcp_sha
    assert host.release_calls==1
    assert host.rollback_calls==0
    receipt=json.loads(next((root/"receipts").glob("*.json")).read_text())
    assert receipt["state"]=="accepted"
    assert receipt["signed_owner_proof"]["payload"]["authorization"]=="authenticated_entra_owner_exact_release"
    assert receipt["signed_owner_proof"]["payload"]["one_release_only"] is True
    assert list((root/"active").glob("*.json"))
    with pytest.raises(native.ComponentReleaseDenied,match="ROLLBACK_NOT_CURRENT"):
        host.controller(root).promote(manifest,exact_owner_proof(manifest))


@pytest.mark.parametrize("phase",(
    "stage_new_inert","capture_checkpoint","disable_legacy",
    "commit_exact_policy","publish_root_acceptance",
    "activate_replacement","postflight",
))
def test_native_signed_release_rolls_back_every_six_unit_phase(tmp_path,phase):
    root,manifest=packet(tmp_path)
    host=SixUnitNativeHost(fail_step=phase)
    with pytest.raises(units.TransactionDenied,match="INJECTED_FAILURE"):
        host.controller(root).promote(manifest,exact_owner_proof(manifest))
    assert host.state==host.before
    assert host.release_calls==1 and host.rollback_calls==1
    receipt=json.loads(next((root/"receipts").glob("*.json")).read_text())
    assert receipt["state"]=="rolled_back"
    assert not list((root/"active").iterdir())
    # A consumed exact grant is never replayable, even after restoration.
    with pytest.raises(OwnerReleaseProofDenied,match="ONE_USE_REPLAY"):
        host.controller(root).promote(manifest,exact_owner_proof(manifest))


def test_native_acceptance_failure_uses_existing_release_rollback(tmp_path):
    root,manifest=packet(tmp_path)
    host=SixUnitNativeHost()
    host.fail_acceptance=True
    with pytest.raises(native.ComponentReleaseDenied,match="ACCEPTANCE_FAILED"):
        host.controller(root).promote(manifest,exact_owner_proof(manifest))
    assert host.state==host.before
    assert host.rollback_calls==1
    assert json.loads(next((root/"receipts").glob("*.json")).read_text())["state"]=="rolled_back"


def test_native_interrupted_transaction_requires_historic_signed_recovery(tmp_path):
    root,manifest=packet(tmp_path)
    host=SixUnitNativeHost(fail_step="activate_replacement",fail_rollback=True)
    with pytest.raises(units.TransactionDenied,match="INJECTED_FAILURE"):
        host.controller(root).promote(manifest,exact_owner_proof(manifest))
    receipt=json.loads(next((root/"receipts").glob("*.json")).read_text())
    assert receipt["state"]=="started"
    with pytest.raises(native.ComponentReleaseDenied,match="UNRESOLVED_TRANSACTION"):
        host.controller(root).promote(manifest,exact_owner_proof(manifest))
    host.fail_rollback=False
    recovered=host.controller(root).recover_interrupted_rollback()
    assert recovered["status"]=="component_rollback_verified"
    assert host.state==host.before
    assert json.loads(next((root/"receipts").glob("*.json")).read_text())["state"]=="rolled_back"


def test_native_release_requires_exact_signed_owner_not_chat_approval(tmp_path):
    root,manifest=packet(tmp_path)
    host=SixUnitNativeHost()
    with pytest.raises((native.ComponentReleaseDenied,PermissionError,TypeError)):
        host.controller(root).promote(manifest,{"message":"I approve"})
    assert host.state==host.before
    assert host.release_calls==0
