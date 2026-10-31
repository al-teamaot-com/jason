# Separate certificate credential for Microsoft Graph User.Create.
# This does not grant Microsoft Graph access by itself; tenant consent remains required.
path "secret/data/connectors/microsoft-graph/production/user-create" {
  capabilities = ["read"]
}
