# Distinct credential reader for a single sealed onboarding request.
# AOT authorization, client boundary and exact hashed request path are
# independently rechecked by the governed runtime before reading this KV item.
path "secret/data/connectors/microsoft-graph/onboarding-passwords/*" {
  capabilities = ["read"]
}
