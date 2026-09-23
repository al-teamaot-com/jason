from __future__ import annotations
from dataclasses import dataclass
from connectors.core.contracts import AuditSink, ConnectorAuthorizationError, ConnectorContext, ConnectorRequest, ConnectorResult, require_capability
from .security_posture import MicrosoftGraphSecurityPostureReader

@dataclass(frozen=True, slots=True)
class MicrosoftGraphSecurityPostureConnector:
    reader: MicrosoftGraphSecurityPostureReader
    bindings: object
    audit: AuditSink
    provider_name="microsoft_graph"
    capabilities=frozenset({"microsoft_graph.authentication_methods.list","microsoft_graph.conditional_access.list","microsoft_graph.directory_roles.list","microsoft_graph.directory_role_members.list"})
    def _tenant(self, context: ConnectorContext) -> str:
        b=self.bindings.find_active_by_jason_identity(jason_identity_id=context.principal_id)
        if b is None or str(getattr(b,"status","") or "").strip()!="active": raise ConnectorAuthorizationError("A unique active Microsoft identity binding is required.")
        tenant=str(getattr(b,"microsoft_tenant_id","") or "").strip()
        if not tenant: raise ConnectorAuthorizationError("The Microsoft identity binding does not identify a tenant.")
        return tenant
    def execute(self, request: ConnectorRequest) -> ConnectorResult:
        require_capability(request,self.capabilities); tenant=self._tenant(request.context); cap=request.context.capability
        self.audit.record("connector.requested",request.context,{"provider":self.provider_name,"operation":cap})
        if cap=="microsoft_graph.authentication_methods.list": data=self.reader.authentication_methods(microsoft_tenant_id=tenant,user_id=str(request.arguments.get("user_id") or ""))
        elif cap=="microsoft_graph.conditional_access.list": data=self.reader.conditional_access_policies(microsoft_tenant_id=tenant,maximum_records=int(request.arguments.get("page_size",100)))
        elif cap=="microsoft_graph.directory_roles.list": data=self.reader.directory_roles(microsoft_tenant_id=tenant,maximum_records=int(request.arguments.get("page_size",100)))
        else: data=self.reader.role_members(microsoft_tenant_id=tenant,role_id=str(request.arguments.get("role_id") or ""),maximum_records=int(request.arguments.get("page_size",100)))
        self.audit.record("connector.completed",request.context,{"provider":self.provider_name})
        return ConnectorResult(capability=cap,provider=self.provider_name,data=data)
