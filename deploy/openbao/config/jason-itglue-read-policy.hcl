# Jason IT Glue read-only connector policy
#
# Grants the itglue-read connector access only to its assigned
# production read-only credential and permits its temporary token
# to revoke itself.

path "secret/data/connectors/it-glue/production/read-only" {
  capabilities = ["read"]
}

path "auth/token/revoke-self" {
  capabilities = ["update"]
}

# No access is granted to:
# - other connector credentials;
# - secret metadata or listing;
# - write, update, delete, or destroy operations;
# - OpenBao administration;
# - token operations affecting other identities.
