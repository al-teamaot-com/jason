#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "http://openbao:8200"
ROLE = Path("/run/jason-secrets/openbao/backup-net/role_id")
SECRET = Path("/run/jason-secrets/openbao/backup-net/secret_id")
PATH = "secret/data/connectors/backup-net/production/read-only"


def login() -> str:
    body = json.dumps({
        "role_id": ROLE.read_text().strip(),
        "secret_id": SECRET.read_text().strip(),
    }).encode()
    req = Request(
        BASE + "/v1/auth/approle/login",
        data=body,
        headers={"Content-Type":"application/json"},
        method="POST",
    )
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["auth"]["client_token"]


def read_version(version: int) -> dict[str, str]:
    token = login()
    try:
        req = Request(
            BASE + "/v1/" + PATH + "?" + urlencode({"version": version}),
            headers={"X-Vault-Token": token, "Accept":"application/json"},
            method="GET",
        )
        with urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())["data"]["data"]
        return {k: str(v) for k, v in data.items()}
    finally:
        req = Request(
            BASE + "/v1/auth/token/revoke-self",
            data=b"{}",
            headers={"X-Vault-Token": token, "Content-Type":"application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10):
                pass
        except Exception:
            pass


v1 = read_version(1)
v2 = read_version(2)
print(json.dumps({
    "client_id_same": v1.get("client_id") == v2.get("client_id"),
    "client_secret_same": v1.get("client_secret") == v2.get("client_secret"),
    "v1_client_id_length": len(v1.get("client_id","")),
    "v2_client_id_length": len(v2.get("client_id","")),
    "v1_client_secret_length": len(v1.get("client_secret","")),
    "v2_client_secret_length": len(v2.get("client_secret","")),
    "secret_values_printed": False
}, indent=2, sort_keys=True))
