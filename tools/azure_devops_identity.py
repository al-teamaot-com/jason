#!/usr/bin/env python3
"""Dedicated certificate-based Entra authentication for Azure DevOps reads.

Local certificate/key must be separately provisioned, with 0600 private-key mode.
Never print credentials, bearer tokens, JWT assertions or HTTP auth responses.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import urllib.parse
import urllib.request
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
CLIENT = "1e480a2a-86e7-4df5-875b-0fe772ac34e0"
EXPECTED_CERT_SHA256 = "37d4299a1215b15283ae9234b9e3e0361821b247d7ea1b7da4d8198c0a7272f7"
DEFAULT_CERT_DIR = Path("/home/al/.config/jason/azure-devops-standby")
_TOKEN_CACHE: tuple[str, float] | None = None


class AzureIdentityError(RuntimeError):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64json(data: dict) -> str:
    return _b64url(json.dumps(data, separators=(",", ":")).encode())


def certificate_assertion(
    *,
    key_path: Path,
    cert_path: Path,
    expected_fingerprint: str = EXPECTED_CERT_SHA256,
    at: int | None = None,
) -> str:
    key_path = Path(key_path)
    if not key_path.is_file() or key_path.is_symlink():
        raise AzureIdentityError("Expected a regular protected certificate key")
    if stat.S_IMODE(key_path.stat().st_mode) != 0o600:
        raise AzureIdentityError("Azure certificate private key permissions must equal 0600")
    try:
        certificate = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
        if certificate.fingerprint(hashes.SHA256()).hex() != expected_fingerprint:
            raise AzureIdentityError("Azure certificate fingerprint mismatch")
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    except AzureIdentityError:
        raise
    except Exception:
        raise AzureIdentityError("Azure certificate or private key cannot be loaded") from None

    issued = int(time.time() if at is None else at)
    audience = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    header = {
        "typ": "JWT", "alg": "RS256",
        "x5t#S256": _b64url(hashlib.sha256(
            certificate.public_bytes(serialization.Encoding.DER)
        ).digest()),
    }
    claims = {
        "aud": audience, "iss": CLIENT, "sub": CLIENT,
        "jti": str(uuid4()), "nbf": issued - 10, "exp": issued + 300,
    }
    unsigned = (_b64json(header) + "." + _b64json(claims)).encode("ascii")
    signature = key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
    return unsigned.decode() + "." + _b64url(signature)


def azure_devops_token(cert_dir: Path = DEFAULT_CERT_DIR) -> str:
    global _TOKEN_CACHE
    cert_dir = Path(cert_dir)
    if cert_dir == DEFAULT_CERT_DIR and _TOKEN_CACHE is not None:
        cached_token, expiry = _TOKEN_CACHE
        if time.monotonic() < expiry - 300:
            return cached_token
    key = cert_dir / "standby-client.key"
    cert = cert_dir / "standby-client.crt"
    assertion = certificate_assertion(key_path=key, cert_path=cert)
    endpoint = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": CLIENT,
        "scope": "https://app.vssps.visualstudio.com/.default",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": assertion,
    }).encode("ascii")
    request = urllib.request.Request(
        endpoint, data=form, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except Exception:
        raise AzureIdentityError("Microsoft Entra certificate token exchange failed") from None
    token = result.get("access_token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token:
        raise AzureIdentityError("Entra did not supply an Azure DevOps access token")
    if cert_dir == DEFAULT_CERT_DIR:
        try:
            lifetime = min(3600, max(1, int(result.get("expires_in", 3600))))
        except (TypeError, ValueError):
            lifetime = 300
        _TOKEN_CACHE = (token, time.monotonic() + lifetime)
    return token
