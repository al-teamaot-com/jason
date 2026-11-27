"""Build and rehearse a two-file upgrade for the installed coordinated controller.

The production caller must supply the existing trusted release transaction,
protected-main inputs, and independently verified one-use Owner approval.
There is no CLI or production entry point in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

from tools.scoped_backport_coordinated_host import INSTALLED, POLICY, REUSABLE_POLICY_FIELDS
from tools.scoped_backport_release import deny, digest, require_sha

ACTION = "upgrade_coordinated_controller_only"


@dataclass(frozen=True)
class RootFile:
    path: Path
    mode: int
    before: bytes
    after: bytes


@dataclass(frozen=True)
class Upgrade:
    candidate_sha: str
    rollback_sha: str
    files: tuple[RootFile, RootFile]

    def scope(self) -> dict:
        return {
            "action": ACTION,
            "candidate_sha": self.candidate_sha,
            "rollback_sha": self.rollback_sha,
            "files": [
                {
                    "path": str(file.path), "mode": format(file.mode, "04o"),
                    "before_sha256": sha256(file.before).hexdigest(),
                    "after_sha256": sha256(file.after).hexdigest(),
                }
                for file in self.files
            ],
        }

    @property
    def scope_sha256(self) -> str:
        return digest(self.scope())


def plan_upgrade(
    candidate_sha: str,
    rollback_sha: str,
    installed_controller: bytes,
    rollback_controller: bytes,
    candidate_controller: bytes,
    installed_policy: bytes,
) -> Upgrade:
    """Bind the replacement and exact rollback bytes without repinning readers."""
    require_sha(candidate_sha, "CONTROLLER_UPGRADE_CANDIDATE")
    require_sha(rollback_sha, "CONTROLLER_UPGRADE_ROLLBACK")
    if candidate_sha == rollback_sha or installed_controller != rollback_controller:
        deny("CONTROLLER_UPGRADE_ROLLBACK_MISMATCH")
    policy = json.loads(installed_policy)
    if (not isinstance(policy, dict) or set(policy) != REUSABLE_POLICY_FIELDS
            or policy["schema_version"] != "3.0"
            or policy["per_release_review_required"] is not True
            or not isinstance(policy["file_sha256"], dict)):
        deny("CONTROLLER_UPGRADE_POLICY_INVALID")

    before_pin = sha256(installed_controller).hexdigest()
    after_pin = sha256(candidate_controller).hexdigest()
    if (policy["file_sha256"].get("host") != before_pin
            or installed_policy.count(before_pin.encode()) != 1
            or before_pin == after_pin):
        deny("CONTROLLER_UPGRADE_HOST_PIN_MISMATCH")
    proposed = installed_policy.replace(before_pin.encode(), after_pin.encode(), 1)
    expected = dict(policy, file_sha256={**policy["file_sha256"], "host": after_pin})
    if json.loads(proposed) != expected:
        deny("CONTROLLER_UPGRADE_POLICY_DELTA")
    return Upgrade(candidate_sha, rollback_sha, (
        RootFile(INSTALLED, 0o444, installed_controller, candidate_controller),
        RootFile(POLICY, 0o600, installed_policy, proposed),
    ))


def apply_under_held_transaction(
    upgrade: Upgrade,
    *,
    revalidate: Callable[[], Upgrade],
    consume_and_record_rollback: Callable[[Upgrade], None],
    replace: Callable[[Path, bytes, bytes, int], None],
    restore: Callable[[list[tuple[Path, bytes, bytes, int]]], None],
    verify: Callable[[Upgrade, bool], None],
) -> None:
    """Use the host's one-use claim and durable rollback before the first write.

    The caller owns the shared transaction lock, listener quiescence, protected
    source/CI checks and verification of the exact signed Owner decision.
    """
    if revalidate() != upgrade:
        deny("CONTROLLER_UPGRADE_SCOPE_CHANGED")
    consume_and_record_rollback(upgrade)

    attempted = []
    try:
        for file in upgrade.files:
            change = (file.path, file.before, file.after, file.mode)
            attempted.append(change)
            replace(*change)
        verify(upgrade, False)
    except BaseException:
        restore(attempted)
        verify(upgrade, True)
        raise
