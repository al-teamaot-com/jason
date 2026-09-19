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
