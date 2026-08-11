from __future__ import annotations

import json

from management_api.auth import ManagementAuthenticationFailed
from management_api.service import ManagementReadContext
from management_api.wsgi import ManagementWsgiApp


class FakeService:
    def overview(self, context):
        return {
            "principal": context.principal_id,
            "organization": context.organization_id,
        }

    def system_health(self, context):
        return {"status": "healthy"}

    def list_capabilities(self, context):
        return []

    def list_providers(self, context):
        return []

    def search_audit_events(self, context, **kwargs):
        return []


class FakeResolver:
    def __init__(self, context=None, *, deny=False):
        self.context = context
        self.deny = deny

    def resolve(self, environ):
        if self.deny:
            raise ManagementAuthenticationFailed("denied")
        return self.context


def invoke(app, environ):
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(app(environ, start_response))
    return captured, json.loads(body)


def test_http_boundary_requires_authenticated_identity_context():
    app = ManagementWsgiApp(
        FakeService(),
        context_resolver=FakeResolver(deny=True),
    )
    captured, payload = invoke(
        app,
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/management/v0.1/overview",
        },
    )

    assert captured["status"] == "401 Unauthorized"
    assert payload["error"] == "authenticated_identity_required"


def test_http_boundary_projects_only_resolver_context_to_service():
    app = ManagementWsgiApp(
        FakeService(),
        context_resolver=FakeResolver(
            ManagementReadContext(
                principal_id="person-al",
                organization_id="aot",
            )
        ),
    )
    captured, payload = invoke(
        app,
        {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/management/v0.1/overview",
            "HTTP_X_JASON_PRINCIPAL_ID": "spoofed-principal",
            "HTTP_X_JASON_ORGANIZATION_ID": "spoofed-org",
        },
    )

    assert captured["status"] == "200 OK"
    assert payload == {"organization": "aot", "principal": "person-al"}
    assert captured["headers"]["Cache-Control"] == "no-store"


def test_http_boundary_rejects_writes_before_identity_resolution():
    app = ManagementWsgiApp(
        FakeService(),
        context_resolver=FakeResolver(deny=True),
    )
    captured, payload = invoke(
        app,
        {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/management/v0.1/overview",
        },
    )

    assert captured["status"] == "405 Method Not Allowed"
    assert payload["error"] == "read_only_api"
