# Jason Datto RMM governed component-execution credential policy
#
# This policy is intentionally separate from the Datto read-only identity.
# It permits the dedicated execution AppRole to read only the execution
# credential record required for future approved quick-job execution.
#
# The AppRole token is deliberately issued without the OpenBao default policy,
# so the minimum self-revocation capability is granted explicitly. This lets
# the generic secret resolver destroy its short-lived token after one KV read
# without granting any broader token-management authority.

path "secret/data/connectors/datto-rmm/production/execution" {
  capabilities = ["read"]
}

path "auth/token/revoke-self" {
  capabilities = ["update"]
}
