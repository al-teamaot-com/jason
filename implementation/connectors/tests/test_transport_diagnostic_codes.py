import errno
import socket
import ssl
from urllib.error import URLError

from connectors.core.http_transport import _safe_network_failure_code


def test_safe_transport_diagnostic_classifications():
    assert _safe_network_failure_code(URLError(socket.gaierror(-2, 'sensitive hostname'))) == 'DNS_RESOLUTION'
    assert _safe_network_failure_code(URLError(ConnectionRefusedError(errno.ECONNREFUSED, 'secret endpoint'))) == 'CONNECTION_REFUSED'
    assert _safe_network_failure_code(URLError(TimeoutError('secret endpoint'))) == 'NETWORK_TIMEOUT'
    assert _safe_network_failure_code(URLError(ssl.SSLError('private certificate details'))) == 'TLS_FAILURE'
    assert _safe_network_failure_code(OSError(errno.ENETUNREACH, 'secret endpoint')) == 'NETWORK_UNREACHABLE'
    assert _safe_network_failure_code(URLError('https://secret.internal/path?token=private')) == 'NETWORK_IO_FAILURE'
