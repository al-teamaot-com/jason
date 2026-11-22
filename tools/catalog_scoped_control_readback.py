#!/usr/bin/env python3
"""Root-trusted scoped runtime/MCP control readback, never a broad drift waiver.

SOURCE ONLY. Do not install or run as a production watchdog absent separately
approved root source, systemd schedule, manifest and signed Owner transaction.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any,Mapping

from tools.catalog_scoped_promotion import ScopedPromotionDenied,fail,PROTECTED_CONTAINERS

KEYS=frozenset({
    'schema_version','authorization','release_id','snapshot_sha','host_revision',
    'scope_sha256','manifest_sha256','runtime_image_id','mcp_image_id',
    'rollback_runtime_image_id','rollback_mcp_image_id','freeze_sha256',
    'approval_id','owner_principal','protected_containers',
    'status','recorded_at','global_owner_allowlist_unchanged',
})
SHA=re.compile(r'^[a-f0-9]{40}$')
HEX=re.compile(r'^[a-f0-9]{64}$')
IMAGE=re.compile(r'^sha256:[a-f0-9]{64}$')


def validate_overlay(doc:Mapping[str,Any],offer:Mapping[str,Any])->None:
    if not isinstance(doc,Mapping) or set(doc)!=KEYS:
        fail('CONTROL_OVERLAY_SCHEMA_CHANGED')
    for key,expected in (
        ('schema_version','1.0'),
        ('authorization','owner_signed_catalog_scoped_dual_image'),
        ('release_id',offer['release_id']),
        ('snapshot_sha',offer['candidate_sha']),
        ('host_revision',offer['rollback_sha']),
        ('scope_sha256',offer['scope_sha256']),
        ('manifest_sha256',offer['manifest_sha256']),
        ('runtime_image_id',offer['runtime_image_id']),
        ('mcp_image_id',offer['mcp_image_id']),
        ('rollback_runtime_image_id',offer['rollback_runtime_image_id']),
        ('rollback_mcp_image_id',offer['rollback_mcp_image_id']),
        ('freeze_sha256',offer['freeze_sha256']),
        ('protected_containers',list(PROTECTED_CONTAINERS)),
        ('global_owner_allowlist_unchanged',True),
    ):
        if doc.get(key)!=expected:
            fail('CONTROL_OVERLAY_BINDING_MISMATCH')
    if doc.get('status') not in {'scoped_pair_readback_pending',
                                   'scoped_pair_verified'}:
        fail('CONTROL_OVERLAY_STATE_INVALID')
    if (not isinstance(doc.get('approval_id'),str)
            or re.fullmatch(r'owner-mcp-[a-f0-9]{32}',doc['approval_id']) is None
            or not isinstance(doc.get('owner_principal'),str)
            or not doc['owner_principal'].startswith('person-entra-')):
        fail('CONTROL_OVERLAY_OWNER_BINDING_INVALID')


def verify_root_readback(
    *,offer:Mapping[str,Any],overlay:Mapping[str,Any],
    live:Mapping[str,Any],freeze_sha256:str|None,
    original_breaker:Mapping[str,Any],phase:str,
)->dict[str,Any]:
    """Apply exact overlay only to two named containers, never to root PMV4."""
    validate_overlay(overlay,offer)
    if phase not in {'inside_exact_release_lock','steady_frozen'}:
        fail('CONTROL_PHASE_INVALID')
    if (original_breaker.get('circuit_breaker',{}).get('state')!='closed'
            or original_breaker.get('last_known_good',{}).get('manifest',{}).get('revision')!=offer['rollback_sha']):
        fail('CONTROL_ORIGINAL_BASELINE_NOT_CLOSED')
    if phase=='steady_frozen' and freeze_sha256!=offer['freeze_sha256']:
        fail('CONTROL_FREEZE_DRIFT')
    if phase=='inside_exact_release_lock' and freeze_sha256 is not None:
        fail('CONTROL_FREEZE_UNEXPECTEDLY_PRESENT')
    if (live.get('host_revision')!=offer['rollback_sha']
            or live.get('runtime_revision')!=offer['candidate_sha']
            or live.get('mcp_revision')!=offer['candidate_sha']
            or live.get('runtime_image_id')!=offer['runtime_image_id']
            or live.get('mcp_image_id')!=offer['mcp_image_id']
            or live.get('runtime_healthy') is not True
            or live.get('mcp_running') is not True
            or live.get('runtime_catalog_auth_mode')!='jason_managed'
            or live.get('mcp_catalog_grant_profile')!='aot-catalog-self-owner-v1'
            or live.get('global_owner_allowlist')!='person-al'):
        fail('CONTROL_EXACT_IMAGE_OR_IDENTITY_DRIFT')
    running=live.get('protected_services')
    if (not isinstance(running,Mapping) or set(running)!=set(PROTECTED_CONTAINERS)
            or any(running[x] is not True for x in PROTECTED_CONTAINERS)):
        fail('CONTROL_PROTECTED_SERVICE_DEGRADED')
    return {
        'schema_version':'1.0',
        'status':'scoped_readback_pass_not_global_source_alignment',
        'release_id':offer['release_id'],
        'candidate_sha':offer['candidate_sha'],
        'rollback_sha':offer['rollback_sha'],
        'runtime_image_id':offer['runtime_image_id'],
        'mcp_image_id':offer['mcp_image_id'],
        'freeze_restored':phase=='steady_frozen',
        'global_owner_allowlist_unchanged':True,
        'no_new_service_authority':True,
    }
