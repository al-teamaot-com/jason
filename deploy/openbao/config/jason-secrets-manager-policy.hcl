# Jason non-destructive secrets-management policy

# Create, read, update, and soft-delete current secret versions.
path "secret/data/*" {
  capabilities = ["create", "read", "update", "delete"]
}

# List secret paths and inspect version metadata.
# Deliberately excludes delete to prevent removal of all versions.
path "secret/metadata/*" {
  capabilities = ["read", "list"]
}

# Soft-delete selected historical versions.
path "secret/delete/*" {
  capabilities = ["update"]
}

# Restore soft-deleted versions.
path "secret/undelete/*" {
  capabilities = ["update"]
}

# No access is granted to secret/destroy/*.
