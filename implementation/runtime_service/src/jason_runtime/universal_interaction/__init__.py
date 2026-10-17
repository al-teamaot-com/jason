"""Universal interaction contract and inert, opt-in adapters (ADR-013)."""
from .contracts import (
    Interaction, InteractionKind, VisualIntent, FieldType, ActionType,
    Action, Field, Fact, Option, Condition, validate_answers,
)
from .service import (
    UniversalInteractionService, ExistingApprovalGuard, AuthorizedRoute,
    ChannelFeatures, InteractionDelivery, InteractionRejected,
    OrchestrationInteractionJournal,
)
from .teams import ExistingTeamsInteractionAdapter
from .responses import (
    UniversalResponseHandoff, VerifiedReply, ResponseReceipt,
    OrchestrationResponseJournal,
)
from .wire import to_wire
from .owner_requests import interaction_from_owner_approval
