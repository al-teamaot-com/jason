from io import BytesIO

from connectors.datto_rmm.capability_manifest import (
    build_datto_rmm_manifest,
)
from orchestrator.integration_broker import (
    IntegrationBroker,
)
from orchestrator.integration_documentation import (
    LiveIntegrationDocumentationReader,
)


class Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def read(self):
        return self._body


class Broker:
    def __init__(self):
        manifest = (
            build_datto_rmm_manifest()
        )

        self._view = type(
            "View",
            (),
            {
                "integration_id":
                    manifest.integration_id,
                "manifest": manifest,
            },
        )()

    def list_integrations(self):
        return (
            self._view,
        )


def test_live_documentation_reader_uses_manifest_url():
    calls = []

    def opener(
        request,
        timeout,
    ):
        calls.append(
            request.full_url
        )

        return Response(
            b"""
            <html>
              <body>
                <h1>Datto RMM API</h1>
                <p>GET /v2/account/devices</p>
                <p>nextPageUrl</p>
              </body>
            </html>
            """
        )

    reader = (
        LiveIntegrationDocumentationReader(
            broker=Broker(),
            opener=opener,
        )
    )

    document = reader.read(
        "datto_rmm"
    )

    assert (
        "/2SETUP/APIv2.htm"
        in document.source_url
    )

    assert (
        "GET /v2/account/devices"
        in document.content
    )

    assert (
        "nextPageUrl"
        in document.content
    )

    # Second read is served from cache.
    again = reader.read(
        "datto_rmm"
    )

    assert again is document
    assert len(calls) == 1
