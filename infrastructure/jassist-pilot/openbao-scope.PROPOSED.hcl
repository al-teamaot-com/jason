# SOURCE ONLY — NOT INSTALLED. Least-privilege future J-Assist pilot AppRole.
# The production OpenBao role and policies remain unchanged.
# KV-v2 read paths ONLY. No list, create, update, patch, delete or sudo.
path "secret/data/pilots/jassist/nonproduction/session-encryption" {
  capabilities = ["read"]
}
path "secret/data/pilots/jassist/nonproduction/evidence-encryption" {
  capabilities = ["read"]
}
