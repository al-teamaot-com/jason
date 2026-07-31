# Jason OpenBao least-privilege Raft backup policy

# Inspect the Raft cluster and confirm the active leader.
path "sys/storage/raft/configuration" {
  capabilities = ["read"]
}

# Create a Raft snapshot.
path "sys/storage/raft/snapshot" {
  capabilities = ["read"]
}

# Permit a temporary backup token to revoke only itself.
path "auth/token/revoke-self" {
  capabilities = ["update"]
}

# No update capability is granted on the Raft snapshot endpoint,
# so snapshot restoration is denied.
#
# No access is granted to snapshot-force, secrets, token revocation
# for other identities, or other administrative paths.
