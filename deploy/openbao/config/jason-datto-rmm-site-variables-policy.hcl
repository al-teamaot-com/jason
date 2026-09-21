# Jason Datto RMM governed site-variable credential policy
#
# This policy is intentionally separate from the Datto read-only and component-
# execution identities. It permits the dedicated site-variable AppRole to read
# only the provider credential used for governed site-variable create/update.
#
# Tokens are issued without the OpenBao default policy, so explicit self-revoke
# is required for the generic secret resolver to destroy its short-lived token.

path "secret/data/connectors/datto-rmm/production/site-variables" {
  capabilities = ["read"]
}

path "auth/token/revoke-self" {
  capabilities = ["update"]
}
