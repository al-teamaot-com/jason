from dataclasses import dataclass
from connectors.microsoft_graph.security_posture import MicrosoftGraphSecurityPostureReader
@dataclass
class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id: str): return "token"
@dataclass
class Transport:
    response: dict
    call: dict|None=None
    def request(self, **kwargs): self.call=kwargs; return self.response

def test_authentication_methods_projects_only_method_type_and_id():
    t=Transport({"value":[{"id":"m1","@odata.type":"#microsoft.graph.microsoftAuthenticatorAuthenticationMethod","secret":"must-not-project"}]})
    r=MicrosoftGraphSecurityPostureReader(tokens=Tokens(),transport=t).authentication_methods(microsoft_tenant_id="tenant",user_id="user/1")
    assert r["items"]==[{"id":"m1","method_type":"#microsoft.graph.microsoftAuthenticatorAuthenticationMethod"}]
    assert t.call["url"].endswith("/users/user%2F1/authentication/methods")

def test_conditional_access_is_bounded_and_projected():
    t=Transport({"value":[{"id":"p1","displayName":"Require MFA","state":"enabled","conditions":{"users":{}},"grantControls":{"builtInControls":["mfa"]}}]})
    r=MicrosoftGraphSecurityPostureReader(tokens=Tokens(),transport=t).conditional_access_policies(microsoft_tenant_id="tenant",maximum_records=25)
    assert r["count"]==1 and r["items"][0]["display_name"]=="Require MFA"
    assert t.call["params"]=={"$top":25}

def test_directory_role_members_are_exact_role_scoped():
    t=Transport({"value":[{"id":"u1","displayName":"Admin","userPrincipalName":"a@example.com","accountEnabled":True,"@odata.type":"#microsoft.graph.user"}]})
    r=MicrosoftGraphSecurityPostureReader(tokens=Tokens(),transport=t).role_members(microsoft_tenant_id="tenant",role_id="role/1",maximum_records=10)
    assert r["role_id"]=="role/1" and r["count"]==1
    assert "/directoryRoles/role%2F1/members" in t.call["url"]


def test_directory_roles_does_not_send_unsupported_top_and_bounds_locally():
    t=Transport({"value":[
        {"id":"role1","displayName":"Reader","roleTemplateId":"template1"},
        {"id":"role2","displayName":"Administrator","roleTemplateId":"template2"},
    ]})
    data=MicrosoftGraphSecurityPostureReader(tokens=Tokens(),transport=t).directory_roles(
        microsoft_tenant_id="tenant",maximum_records=1)
    assert t.call["url"].endswith("/directoryRoles")
    assert t.call["params"] == {}
    assert data["count"]==1 and data["truncated"] is True
    assert data["items"]==[{"id":"role1","display_name":"Reader","role_template_id":"template1"}]


def test_directory_role_members_no_unsupported_top_and_preserves_scope():
    t=Transport({"value":[
        {"id":"member1","displayName":"Alice","userPrincipalName":"a@example.invalid"},
        {"id":"member2","displayName":"Bob","userPrincipalName":"b@example.invalid"},
    ]})
    data=MicrosoftGraphSecurityPostureReader(tokens=Tokens(),transport=t).role_members(
        microsoft_tenant_id="tenant",role_id="role/1",maximum_records=1)
    assert t.call["url"].endswith("/directoryRoles/role%2F1/members")
    assert t.call["params"] == {}
    assert data["count"]==1 and data["truncated"] is True
    assert data["items"][0]["id"]=="member1"


def test_directory_roles_refuses_unexpected_provider_records():
    from connectors.core.contracts import ConnectorTransportError
    for records in ({"value":{"unexpected":"shape"}}, {"value":[{"id":"ok"},"bad"]}):
        t=Transport(records)
        try:
            MicrosoftGraphSecurityPostureReader(tokens=Tokens(),transport=t).directory_roles(microsoft_tenant_id="tenant",maximum_records=2)
        except ConnectorTransportError:
            pass
        else:
            assert False, "Invalid provider record must fail closed"
