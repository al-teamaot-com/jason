# Jason administrative policy
#
# Provides full OpenBao administration through a named policy.
# Routine services and agents must never receive this policy.

path "*" {
  capabilities = ["create", "read", "update", "patch", "delete", "list", "sudo"]
}
