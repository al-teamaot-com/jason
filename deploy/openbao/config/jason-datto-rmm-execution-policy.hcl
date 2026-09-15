# Jason Datto RMM governed component-execution credential policy
#
# This policy is intentionally separate from the Datto read-only identity.
# It permits the dedicated execution AppRole to read only the execution
# credential record required for future approved quick-job execution.

path "secret/data/connectors/datto-rmm/production/execution" {
  capabilities = ["read"]
}
