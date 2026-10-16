#!/usr/bin/env python3
"""Non-force GitHub-primary Azure standby sync with per-ref verified receipts.

Azure Repos rejects Git atomic pushes. Partial progress is observable and
recoverable; no success is reported until every source ref is verified.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
from typing import Callable
from tools.standby_governed_sync import MirrorBlocked, approved_authority, build_updates

AZURE_URL = "https://dev.azure.com/aotva/Jason-Standby/_git/Jason-Standby"


def secure_git_env(token: str) -> dict:
    if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
        raise MirrorBlocked("invalid Azure credential")
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            del env[name]
    env.update({"GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "http.https://dev.azure.com/.extraheader",
        "GIT_CONFIG_VALUE_0": "AUTHORIZATION: bearer " + token,
        "GIT_CONFIG_KEY_1": "credential.interactive",
        "GIT_CONFIG_VALUE_1": "never",
        "GIT_TERMINAL_PROMPT": "0", "GIT_TRACE": "0",
        "GIT_TRACE_PACKET": "0", "GIT_CURL_VERBOSE": "0"})
    return env


class PartialSyncBlocked(MirrorBlocked):
    def __init__(self, reason: str, verified_refs: int):
        self.verified_refs = verified_refs
        super().__init__(reason + f"; independently verified refs before failure={verified_refs}")


def guarded_push(*, bare_source: Path, github: dict, azure_before: dict,
                 ancestor: Callable, read_azure: Callable, token_provider: Callable,
                 authority_path: Path, runner: Callable = subprocess.run) -> dict:
    approved_authority(authority_path)
    source = Path(bare_source).resolve()
    if not source.is_dir() or not (source / "HEAD").is_file():
        raise MirrorBlocked("dedicated bare source mirror missing")
    updates, plan_result = build_updates(github, azure_before, ancestor)
    if read_azure() != azure_before:
        raise MirrorBlocked("Azure refs changed since source snapshot")
    approved_authority(authority_path)
    verified_count = 0
    credential_env = None
    for row in updates:
        approved_authority(authority_path)
        before = read_azure()
        ref = row["name"]
        expected = row["oldObjectId"]
        if (before.get(ref) or "0" * 40) != expected:
            raise PartialSyncBlocked("Azure ref moved concurrently", verified_count)
        if any(before.get(k) != v for k, v in azure_before.items() if k not in github):
            raise PartialSyncBlocked("Azure-only ref changed", verified_count)
        if credential_env is None:
            credential_env = secure_git_env(token_provider())
        args = ["git", "--git-dir=" + str(source), "push",
                AZURE_URL, ref + ":" + ref]
        try:
            result = runner(args, env=credential_env, capture_output=True,
                            text=True, timeout=600)
        except Exception:
            raise PartialSyncBlocked("Azure Git transport error", verified_count) from None
        if result.returncode != 0:
            raise PartialSyncBlocked("Azure rejected non-force ref update", verified_count)
        after = read_azure()
        if after.get(ref) != row["newObjectId"]:
            raise PartialSyncBlocked("Azure ref readback failed", verified_count)
        verified_count += 1
    after = read_azure()
    if any(after.get(k) != v for k, v in github.items()):
        raise PartialSyncBlocked("Final Azure ref inventory differs from GitHub", verified_count)
    if any(after.get(k) != v for k, v in azure_before.items() if k not in github):
        raise PartialSyncBlocked("Azure-only refs not preserved", verified_count)
    return {"verified": True, "pushed_refs": verified_count,
            "preserved_azure_only": len(plan_result["preserve_azure_only"]),
            "non_atomic": True}
