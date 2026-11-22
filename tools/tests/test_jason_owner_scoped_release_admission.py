from copy import deepcopy
import json
from pathlib import Path
import pytest
from tools.jason_owner_scoped_release_admission import validate,ScopedOwnerDenied,verify_source,SRC,ROLLBACK
from tools.jason_owner_image_rehearsal import validate as rehearsal_validate

ROOT=Path(__file__).resolve().parents[2]

def manifest():
 return json.loads((ROOT/'config/jason-owner-only-scoped-release.json').read_text())

def test_exact_owner_only_release_manifest_accepted_without_grant():
 m=validate(manifest())
 assert m['new_mcp_env']=={'JASON_AOT_ADMIN_APPROVER_PROFILE':'jason-owner-v1'}
 assert m['native_production_release_authorized'] is False
 assert m['provider_writes_authorized'] is False
 assert m['runtime_replacement_authorized'] is False
 assert m['one_use_signed_owner_approval_required'] is True

def test_source_revision_is_exact_lkg_descendant():
 assert verify_source(ROOT,manifest())['code_file_count']==8

@pytest.mark.parametrize('bad',[
 {'profile':'wildcard-owner'},
 {'owner_object_id':'c848022d-e13b-4457-84b0-e2f5c00dcaf6'},
 {'microsoft_admin_object_id':'bee80bdc-ffb0-4c50-b453-c09d4d411f5f'},
 {'owner_tenant_id':'00000000-0000-0000-0000-000000000000'},
 {'candidate_sha':ROLLBACK},
 {'rollback_sha':SRC},
 {'native_production_release_authorized':True},
 {'provider_writes_authorized':True},
 {'pmv4_core_replacement_authorized':True},
 {'runtime_replacement_authorized':True},
 {'one_use_signed_owner_approval_required':False},
 {'new_mcp_env':{'JASON_AOT_ADMIN_APPROVER_PROFILE':'person-al'}},
 {'source_scope_files':['implementation/mcp_service/src/jason_mcp/server.py']},
 {'freeze_sha256':'0'*64},
 {'candidate_mcp_image_id':'invalid'},
])
def test_scope_expansion_and_wrong_identity_fail_closed(bad):
 m=manifest();m.update(bad)
 with pytest.raises(ScopedOwnerDenied):validate(m)

def test_additional_unapproved_source_file_denied():
 m=manifest();m['source_file_sha256']['implementation/runtime_service/src/jason_runtime/composition.py']='0'*64
 with pytest.raises(ScopedOwnerDenied):validate(m)

def test_dockerfile_preserves_base_layers_and_exact_source_label():
 s=(ROOT/'infrastructure/jason-mcp/Dockerfile.owner-scoped-preprod').read_text()
 assert 'SOURCE_REV=ec891ae49428357ccae8fa3b990c021a124b41d9' in s
 assert 'LABEL com.teamaot.jason.source_revision=${SOURCE_REV}' in s
 assert 'COPY implementation/mcp_service/src/jason_mcp/server.py' in s
 assert 'COPY implementation/runtime_service' not in s
 assert 'COPY config/' not in s
 assert 'FROM ${BASE_IMAGE}' in s

def test_rehearsal_rejects_unsafe_production_authority():
 r={'schema_version':'1.0','purpose':'jason-owner-only-mcp-isolated-rollback-rehearsal',
    'candidate_sha':SRC,'rollback_sha':ROLLBACK,
    'candidate_image_id':manifest()['candidate_mcp_image_id'],
    'rollback_image_id':manifest()['rollback_mcp_image_id'],
    'candidate_server_sha256':manifest()['candidate_server_sha256'],
    'protected_names':['jason-runtime','jason-mcp-pilot','jason-pmv4-ticket-core','jason-pmv4-shadow-gateway','jason-teams-gateway'],
    'provider_writes_authorized':False,'runtime_replacement_authorized':False,
    'production_release_authorized':False}
 assert rehearsal_validate(r)['production_release_authorized'] is False
 r['production_release_authorized']=True
 with pytest.raises(ValueError):rehearsal_validate(r)
