"""Synthetic source-only v2 admission fixture; NEVER a production release receipt."""
from copy import deepcopy
from hashlib import sha256
import json


def synthetic_fresh_v2(manifest, historical):
    d=deepcopy(historical)
    source=d['protected_source']
    source['verified_main_sha']='3cae441ef7d37d5e461c00efc101d0b7953e7a43'
    source['verified_protected_feature_sha']=manifest['protected_feature_sha']
    source['snapshot_source_sha']=manifest['snapshot_sha']
    source['rollback_source_sha']=manifest['rollback_sha']
    source['changed_files']=manifest['changed_files']
    source['source_diff_sha256']=manifest['scope_sha256']
    source['shared_function_count']=6
    source['blob_equality_count']=7
    dual=d['dual_image_rollback']
    for key,manifest_key in (
        ('candidate_runtime_image_id','runtime_image_id'),
        ('candidate_mcp_image_id','mcp_image_id'),
        ('rollback_runtime_image_id','rollback_runtime_image_id'),
        ('rollback_mcp_image_id','rollback_mcp_image_id'),
        ('rollback_sha','rollback_sha'),('freeze_sha256','freeze_sha256'),
    ):
        dual[key]=manifest[manifest_key]
    d['protected_ci']['source_sha']=manifest['protected_feature_sha']
    d['native_readonly_preflight']['runtime']['image_id']=manifest['runtime_image_id']
    d['native_readonly_preflight']['mcp']['image_id']=manifest['mcp_image_id']
    d['receipt_sha256']=sha256(json.dumps({k:v for k,v in d.items() if k!='receipt_sha256'},
        sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    return d
