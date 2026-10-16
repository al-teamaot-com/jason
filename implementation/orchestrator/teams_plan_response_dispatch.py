"""Safe adaptation of runtime approval intents to authenticated plan processing.

The callback's approval_id is only a lookup key. Identity, request, and proposal
are resolved from trusted server dependencies rather than the Teams payload.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class UniversalPlanResponseDispatch:
    service: Any
    proposal_repository: Any
    request_repository: Any
    verified_token_source: Any

    def handle(self, *, approval_id: str, **untrusted_payload):
        if not approval_id.startswith('planapproval-'):
            raise PermissionError('not a universal plan approval')
        # No identity token, original request, or plan scope is accepted from a card.
        # Explicit actor binding is mandatory: an approval ID is never a credential.
        tenant_id = untrusted_payload.get('microsoft_tenant_id')
        object_id = untrusted_payload.get('microsoft_object_id')
        if not tenant_id or not object_id:
            raise PermissionError('authenticated actor context required')
        channel_response_id = untrusted_payload.get('channel_response_id', '')
        if not channel_response_id:
            raise PermissionError('authenticated interaction response identifier required')
        token = self.verified_token_source.require(approval_id, tenant_id=tenant_id,
            object_id=object_id, channel_response_id=channel_response_id)
        # Verify the trusted token independently, including its actor binding.
        # An approval ID and a machine-authenticated envelope do not prove the
        # responding human's identity on their own.
        verifier = self.service.teams_flow.token_verifier
        principal = verifier.verify(token)
        if principal.tenant_id != tenant_id or principal.object_id != object_id:
            raise PermissionError('Teams actor does not match verified Microsoft principal')
        original_request = self.request_repository.require(approval_id)
        if not getattr(original_request, 'organization_id', None):
            raise PermissionError('stored governed request has no organization')
        now = datetime.now(timezone.utc)
        return self.service.handle_stored_response(
            proposal_repository=self.proposal_repository,
            token=token,
            payload={'approval_id': approval_id,
                     'decision': untrusted_payload.get('decision', ''),
                     'organization_id': original_request.organization_id,
                     'channel_response_id': channel_response_id},
            original_request=original_request,
            decided_at=now,
            now=now,
        )
