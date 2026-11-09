"""Synthetic, non-AOT identities for V5 governance regression tests."""
from jason_runtime.release_v5_aot_policy import CHANNEL
AOT_TENANT = "11111111-1111-4111-8111-111111111111"
AOT_REQUESTER_OID = "22222222-2222-4222-8222-222222222222"
AOT_ADMIN_OID = "33333333-3333-4333-8333-333333333333"
AOT_REQUESTER_UPN = "requester@example.org"
AOT_ADMIN_UPN = "admin@example.org"
AOT_OWNER_ROLE = "person-al"  # Synthetic legacy test identity only
ORIGIN = "https://approvals.example.org"
NOTICE_URL = ORIGIN + "/admin/release-approval"
CALLBACK_URL = NOTICE_URL + "/callback"
