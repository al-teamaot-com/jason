#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "implementation"))

from connectors.convergence_command import OperationalConvergenceCommand, OperationalConvergenceRunner
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.datto_rmm.connector import DattoRmmConnector
from connectors.it_glue.connector import ItGlueConnector

from datto_rmm_device_discovery import SanitizedAudit as DattoAudit
from datto_rmm_device_discovery import UrlLibJsonTransport as DattoTransport
from it_glue_configuration_discovery import SanitizedAudit as ItGlueAudit
from it_glue_configuration_discovery import UrlLibJsonTransport as ItGlueTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the bounded live Datto-managed-device authority proof while "
            "treating IT Glue as documentation evidence only."
        )
    )
    parser.add_argument("--live-read", action="store_true")
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--configuration-id", required=True)
    parser.add_argument("--search", required=True)
    parser.add_argument(
        "--match-attribute",
        action="append",
        dest="match_attributes",
        default=[],
        help="Governed attribute used only to corroborate the IT Glue documentation mapping.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    match_attributes = tuple(args.match_attributes or ("serial_number",))

    if not args.live_read:
        print(
            json.dumps(
                {
                    "provider_authority": "datto_rmm",
                    "authority_scope": "rmm_managed_device_identity_and_operational_state",
                    "it_glue_role": "documentation_observation",
                    "candidate_limit": 1,
                    "configuration_id_supplied": bool(args.configuration_id.strip()),
                    "search_supplied": bool(args.search.strip()),
                    "matched_attributes": list(match_attributes),
                    "network_contacted": False,
                    "provider_credentials_used": False,
                    "raw_provider_payload_persisted": False,
                    "status": "credential_safe_preflight",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    it_glue_audit = ItGlueAudit()
    datto_audit = DattoAudit()

    it_glue = ItGlueConnector(
        secrets=OpenBaoSecretResolver(
            base_url="http://127.0.0.1:8200",
            role_id_path=Path(
                "/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/role-id"
            ),
            secret_id_path=Path(
                "/opt/jason/bootstrap/secrets/openbao/itglue-read-approle/secret-id"
            ),
        ),
        transport=ItGlueTransport(),
        audit=it_glue_audit,
    )
    datto = DattoRmmConnector(
        secrets=OpenBaoSecretResolver(
            base_url="http://127.0.0.1:8200",
            role_id_path=Path(
                "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/role-id"
            ),
            secret_id_path=Path(
                "/opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/secret-id"
            ),
        ),
        transport=DattoTransport(),
        audit=datto_audit,
    )

    observation = OperationalConvergenceRunner(
        {"it_glue": it_glue, "datto_rmm": datto}
    ).run(
        OperationalConvergenceCommand(
            organization_id=args.organization_id,
            principal_id="operator-al",
            correlation_id="managed-device-authority-live-proof",
            configuration_id=args.configuration_id,
            search_hint=args.search,
            matched_attributes=match_attributes,
            confidence=1.0,
            candidate_limit=1,
        )
    )

    authority = observation.managed_device_authority
    relationship = observation.relationship_evidence

    output = {
        "authoritative_provider": authority.authoritative_provider,
        "authority_scope": authority.authority_scope,
        "managed_device": {
            "provider": authority.device.provider,
            "resource_type": authority.device.resource_type,
            "external_id": authority.device.external_id,
            "source_authority": authority.device.source_authority,
            "approved_identity_attributes": dict(authority.device.attributes),
        },
        "documentation_relationship_status": observation.relationship_status,
        "documentation_relationship_reason": observation.relationship_reason,
        "it_glue_audit_events": it_glue_audit.events,
        "datto_audit_events": datto_audit.events,
        "network_contacted": True,
        "provider_credentials_used": True,
        "raw_provider_payload_persisted": False,
        "raw_provider_payload_printed": False,
        "canonical_object_created": False,
        "canonical_relationship_promoted": False,
        "provider_mutation_performed": False,
        "status": "pass",
    }

    if relationship is not None:
        output["documentation_relationship"] = {
            "source_provider": relationship.source.provider,
            "source_external_id": relationship.source.external_id,
            "target_provider": relationship.target.provider,
            "target_external_id": relationship.target.external_id,
            "canonical_relationship": relationship.canonical_relationship,
            "verification": relationship.verification.value,
            "confidence": relationship.confidence,
            "matched_attributes": relationship.metadata.get("matched_attributes", "")
            if relationship.metadata
            else "",
        }

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
