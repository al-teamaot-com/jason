from connectors.microsoft_graph.consent import (
    MicrosoftAdminConsentRequest,
    MicrosoftAdminConsentResult,
    MicrosoftConsentConfiguration,
    MicrosoftConsentDeniedError,
    MicrosoftConsentError,
    MicrosoftConsentValidationError,
    build_admin_consent_request,
    parse_admin_consent_callback,
)

__all__ = [
    "MicrosoftAdminConsentRequest",
    "MicrosoftAdminConsentResult",
    "MicrosoftConsentConfiguration",
    "MicrosoftConsentDeniedError",
    "MicrosoftConsentError",
    "MicrosoftConsentValidationError",
    "build_admin_consent_request",
    "parse_admin_consent_callback",
]
