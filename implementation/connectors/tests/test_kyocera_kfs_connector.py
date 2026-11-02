from __future__ import annotations

import base64

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.kyocera_kfs import KFS_DEFAULT_API_URL, KyoceraKfsConnector


class FakeSecrets:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def resolve(self, logical_name, context):
        self.calls.append(logical_name)
        return dict(self.values)


class FakeTransport:
    def request(self, **kwargs):
        raise AssertionError("KFS session connector must not use the stateless transport")


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


class FakeSessionClient:
    calls = []

    def __init__(self, credentials):
        self.credentials = credentials

    def call(self, path, body):
        self.calls.append((path, dict(body)))
        if path == "/KFS/GroupList":
            return {
                "grpTree": {"topGroups": ["root-1"]},
                "groups": [{"groupId": "root-1"}],
                "status": {"code": 200},
            }
        if path == "/KFS/DeviceList":
            return {
                "devices": [
                    {
                        "groupId": "root-1",
                        "deviceId": "dev-1",
                        "attributes": {
                            "serialNumber": "ABC123",
                            "modelName": "TASKalfa 3554ci",
                            "assetNumber": "AOT-9001",
                        },
                        "counters": {"total": 12345},
                    }
                ],
                "status": {"code": 200},
            }
        if path == "/KFS/Device":
            return {
                "devices": [{"deviceId": body["device"], "counters": {"total": 12345}}],
                "status": {"code": 200},
            }
        if path == "/KFS/DeviceLogList":
            return {
                "devices": [{"deviceId": "dev-1", "logs": [{"detail": "string-errorcode_all"}]}],
                "status": {"code": 200},
            }
        return {"status": {"code": 200}}


def credentials():
    return {
        "api_url": KFS_DEFAULT_API_URL,
        "request_from": "REQUEST-FROM",
        "request_to": "KFS_US",
        "authorization": "Basic opaque",
        "kfs_username": "apiuser",
        "kfs_password": "secret",
    }


def context(capability, mode="observe", *, organization_id="aot", client_id=None):
    return ConnectorContext(
        correlation_id="corr-kfs-001",
        principal_id="tech-al",
        organization_id=organization_id,
        client_id=client_id,
        capability=capability,
        mode=mode,
    )


def build(values=None):
    FakeSessionClient.calls.clear()
    secrets = FakeSecrets(values or credentials())
    audit = FakeAudit()
    connector = KyoceraKfsConnector(
        secrets,
        FakeTransport(),
        audit,
        client_factory=FakeSessionClient,
    )
    return connector, secrets, audit


def test_device_search_uses_group_list_and_root_scope():
    connector, secrets, _ = build()
    result = connector.execute(
        ConnectorRequest(
            context("kyocera_kfs.device.search"),
            {"serial_number": "ABC123"},
        )
    )
    assert result.data["matched_count"] == 1
    assert result.data["devices"][0]["deviceId"] == "dev-1"
    assert FakeSessionClient.calls[0][0] == "/KFS/GroupList"
    path, body = FakeSessionClient.calls[1]
    assert path == "/KFS/DeviceList"
    assert body["scope"] == 1
    assert body["deviceAttrIds"] == ["all"]
    assert secrets.calls == ["kyocera_kfs.readonly"]


def test_meter_read_uses_device_endpoint_and_all_counters():
    connector, _, audit = build()
    result = connector.execute(
        ConnectorRequest(
            context("kyocera_kfs.meters.get"),
            {"device_id": "dev-1"},
        )
    )
    assert result.data["devices"][0]["counters"]["total"] == 12345
    path, body = FakeSessionClient.calls[-1]
    assert path == "/KFS/Device"
    assert body["BODID"] == "Global_KFS_Pull_Device"
    assert body["counters"] == ["all"]
    assert audit.events[0][1]["operation"] == "meters_get"


def test_meter_read_resolves_serial_number_before_device_read():
    connector, _, _ = build()
    result = connector.execute(
        ConnectorRequest(
            context("kyocera_kfs.meters.get"),
            {"serial_number": "ABC123"},
        )
    )
    assert result.data["devices"][0]["deviceId"] == "dev-1"
    paths = [path for path, _ in FakeSessionClient.calls]
    assert paths[:2] == ["/KFS/GroupList", "/KFS/DeviceList"]
    assert paths[-1] == "/KFS/Device"
    assert FakeSessionClient.calls[-1][1]["device"] == "dev-1"


def test_alert_search_uses_device_log_list_for_group():
    connector, _, _ = build()
    connector.execute(
        ConnectorRequest(
            context("kyocera_kfs.alerts.list"),
            {"group_id": "root-1"},
        )
    )
    path, body = FakeSessionClient.calls[-1]
    assert path == "/KFS/DeviceLogList"
    assert body["groupTreeState"] == 3


def test_missing_manager_login_fails_closed():
    values = credentials()
    del values["kfs_password"]
    connector, _, _ = build(values)
    with pytest.raises(ConnectorConfigurationError, match="kfs_password"):
        connector.execute(
            ConnectorRequest(
                context("kyocera_kfs.meters.get"),
                {"device_id": "dev-1"},
            )
        )


def test_manager_login_must_not_equal_gateway_basic_pair():
    values = credentials()
    values["kfs_username"] = "gateway-id"
    values["kfs_password"] = "gateway-password"
    raw = b"gateway-id:gateway-password"
    values["authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    connector, _, _ = build(values)
    with pytest.raises(ConnectorConfigurationError, match="must be distinct"):
        connector.execute(
            ConnectorRequest(
                context("kyocera_kfs.meters.get"),
                {"device_id": "dev-1"},
            )
        )
    assert FakeSessionClient.calls == []


def test_client_scoped_request_is_rejected_before_secret_resolution():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="AOT-internal"):
        connector.execute(
            ConnectorRequest(
                context("kyocera_kfs.meters.get", client_id="client-1"),
                {"device_id": "dev-1"},
            )
        )
    assert secrets.calls == []
    assert FakeSessionClient.calls == []


def test_non_aot_request_is_rejected_before_secret_resolution():
    connector, secrets, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="AOT-internal"):
        connector.execute(
            ConnectorRequest(
                context("kyocera_kfs.meters.get", organization_id="other"),
                {"device_id": "dev-1"},
            )
        )
    assert secrets.calls == []
    assert FakeSessionClient.calls == []


def test_non_observe_mode_is_rejected_before_provider_call():
    connector, _, _ = build()
    with pytest.raises(ConnectorAuthorizationError, match="read-only"):
        connector.execute(
            ConnectorRequest(
                context("kyocera_kfs.meters.get", mode="execute"),
                {"device_id": "dev-1"},
            )
        )
    assert FakeSessionClient.calls == []


def test_kfs_http_error_classification_retains_status_without_secret_material():
    from urllib.error import HTTPError
    from connectors.core.contracts import ConnectorTransportError
    from connectors.kyocera_kfs.client import KyoceraKfsSessionClient

    class FailedOpener:
        def open(self, request, timeout):
            raise HTTPError(
                url="https://api.kyods.com/KFS/Login", code=403,
                msg="potentially-secret-provider-error", hdrs=None, fp=None,
            )

    client=KyoceraKfsSessionClient(credentials(),opener=FailedOpener())
    with pytest.raises(ConnectorTransportError) as error:
        client._post("/KFS/Login", {"password":"test-do-not-print"})
    assert error.value.error_code=="PROVIDER_HTTP_STATUS_403"
    assert error.value.status_code==403
    assert error.value.service=="kyocera_kfs"
    assert "test-do-not-print" not in str(error.value)
    assert "potentially-secret-provider-error" not in str(error.value)


def test_kfs_application_status_failure_is_not_falsely_classified_as_http_error():
    from connectors.kyocera_kfs.client import (
        KyoceraKfsApplicationStatusError, KyoceraKfsSessionClient,
    )
    for value,expected in (
        (401,"KFS_APPLICATION_STATUS_401"),
        (503,"KFS_APPLICATION_STATUS_503"),
        ("private message","KFS_APPLICATION_STATUS_UNKNOWN"),
    ):
        with pytest.raises(KyoceraKfsApplicationStatusError) as error:
            KyoceraKfsSessionClient._require_success(
                {"status":{"code":value,"secret":"private"}}, "KFS login",
            )
        assert error.value.error_code==expected
        assert "private message" not in str(error.value)
        assert "private" not in str(error.value)
        assert error.value.status_code is None


def test_kfs_success_status_preserves_read_behavior():
    from connectors.kyocera_kfs.client import KyoceraKfsSessionClient
    KyoceraKfsSessionClient._require_success({"status":{"code":200}},"KFS login")


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (TimeoutError("hidden-credential-content"), "KFS_NETWORK_TIMEOUT"),
        (ConnectionRefusedError("hidden-credential-content"), "KFS_CONNECTION_REFUSED"),
        (OSError("hidden-credential-content"), "KFS_NETWORK_IO_FAILURE"),
    ],
)
def test_active_kfs_session_client_reports_safe_network_diagnostic(failure, expected_code):
    from connectors.kyocera_kfs.client import KyoceraKfsSafeResponseError, KyoceraKfsSessionClient

    class RaisingOpener:
        def open(self, request, timeout):
            raise failure

    client=KyoceraKfsSessionClient(credentials(),opener=RaisingOpener())
    with pytest.raises(KyoceraKfsSafeResponseError) as captured:
        client._post("/KFS/DeviceList", {"password":"another-secret"})
    error=captured.value
    assert error.error_code==expected_code
    assert error.service=="kyocera_kfs"
    assert "hidden-credential-content" not in str(error)
    assert "another-secret" not in str(error)


def test_active_kfs_session_client_distinguishes_dns_and_tls():
    import socket,ssl
    from urllib.error import URLError
    from connectors.kyocera_kfs.client import KyoceraKfsSafeResponseError, KyoceraKfsSessionClient

    for reason, expected in (
        (socket.gaierror(socket.EAI_NONAME,"secret-provider-address"), "KFS_DNS_RESOLUTION"),
        (ssl.SSLError("secret-invalid-certificate"), "KFS_TLS_FAILURE"),
    ):
        class RaisingOpener:
            def open(self, request, timeout):
                raise URLError(reason)
        client=KyoceraKfsSessionClient(credentials(),opener=RaisingOpener())
        with pytest.raises(KyoceraKfsSafeResponseError) as error:
            client._post("/KFS/Login", {"password":"not-for-logs"})
        assert error.value.error_code==expected
        assert "secret" not in str(error.value)


def test_active_kfs_session_client_distinguishes_invalid_json_and_response_shape():
    from connectors.kyocera_kfs.client import KyoceraKfsSafeResponseError, KyoceraKfsSessionClient

    class Response:
        def __init__(self,raw):self.raw=raw
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self):return self.raw

    class ReturningOpener:
        def __init__(self,raw):self.raw=raw
        def open(self,request,timeout):return Response(self.raw)

    for raw,expected in (
        (b'not-json-hidden-provider-text',"KFS_INVALID_JSON"),
        (b'["not-an-object"]',"KFS_INVALID_RESPONSE_SHAPE"),
    ):
        client=KyoceraKfsSessionClient(credentials(),opener=ReturningOpener(raw))
        with pytest.raises(KyoceraKfsSafeResponseError) as error:
            client._post("/KFS/Login", {"password":"do-not-print"})
        assert error.value.error_code==expected
        assert "not-json-hidden-provider-text" not in str(error.value)
        assert "do-not-print" not in str(error.value)


def test_active_kfs_session_connector_uses_patched_session_client_by_default():
    from connectors.kyocera_kfs.connector import KyoceraKfsConnector
    from connectors.kyocera_kfs.session_connector import KyoceraKfsSessionConnector
    from connectors.kyocera_kfs.client import KyoceraKfsSessionClient
    assert KyoceraKfsConnector is KyoceraKfsSessionConnector
    assert KyoceraKfsSessionConnector.__init__.__kwdefaults__["client_factory"] is KyoceraKfsSessionClient
