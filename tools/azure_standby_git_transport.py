#!/usr/bin/env python3
"""Credential-isolated, non-force Azure standby Git transport.

This module is dormant until called by an authority-gated orchestrator.
No tokens, Git stderr, auth headers, or Azure response bodies are logged.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Callable
from urllib.parse import urlsplit

from tools.standby_governed_sync import MirrorBlocked, approved_authority, build_updates

AZURE_URL = "https://dev.azure.com/aotva/Jason-Standby/_git/Jason-Standby"


def secure_git_env(token: str) -> dict[str, str]:
    if not isinstance(token, str) or not token or "\r" in token or "\n" in token:
        raise MirrorBlocked("invalid Azure credential")
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            del env[key]
    env.update({"GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "http.https://dev.azure.com/.extraheader",
                "GIT_CONFIG_VALUE_0": "AUTHORIZATION: bearer " + token,
                "GIT_CONFIG_KEY_1": "credential.interactive",
                "GIT_CONFIG_VALUE_1": "never",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_TRACE": "0", "GIT_TRACE_PACKET": "0", "GIT_CURL_VERBOSE": "0"})
    return env


def guarded_push(*, bare_source: Path, github: dict, azure_before: dict,
                 ancestor: Callable, read_azure: Callable, token_provider: Callable,
                 authority_path: Path, runner: Callable = subprocess.run) -> dict:
    """Requires fresh GitHub mirror, validated refs, external approval, and Azure readback.

    Git's ordinary push enforces non-fast-forward rejection even on a remote race.
    --atomic is mandatory to prevent a partial group of ref updates.
    """
    approved_authority(authority_path)
    source = Path(bare_source).resolve()
    if not source.is_dir():
        raise MirrorBlocked("source Git mirror missing")
    if not (source / "HEAD").is_file():
        raise MirrorBlocked("source is not a bare Git repository")
    updates, plan_result = build_updates(github, azure_before, ancestor)
    if read_azure() != azure_before:
        raise MirrorBlocked("Azure refs changed since snapshot")
    approved_authority(authority_path)
    if not updates:
        after = read_azure()
        if not all(after.get(ref) == sha for ref, sha in github.items()):
            raise MirrorBlocked("Azure verification mismatch")
        return {"verified": True, "pushed_refs": 0}
    refs = [row["name"] + ":" + row["name"] for row in updates]
    if any(not row["name"].startswith(("refs/heads/", "refs/tags/")) for row in updates):
        raise MirrorBlocked("unsupported ref scope")
    token = token_provider()
    args = ["git", "--git-dir=" + str(source), "push", "--atomic",
            AZURE_URL, *refs]
    try:
        completed = runner(args, env=secure_git_env(token),
                           capture_output=True, text=True, timeout=600)
    except Exception:
        raise MirrorBlocked("Azure Git transport failed") from None
    if completed.returncode != 0:
        raise MirrorBlocked("Azure Git atomic non-force push rejected")
    after = read_azure()
    if any(after.get(ref) != sha for ref, sha in github.items()):
        raise MirrorBlocked("Azure independent readback mismatch")
    if any(after.get(ref) != sha for ref, sha in azure_before.items() if ref not in github):
        raise MirrorBlocked("Azure-only refs changed")
    return {"verified": True, "pushed_refs": len(updates),
            "preserved_azure_only": len(plan_result["preserve_azure_only"])}
