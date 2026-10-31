# One dedicated IT Glue notes-only integration credential (provider-side scope
# is determined by the IT Glue account/key and must be independently verified).
path "secret/data/connectors/it-glue/production/configuration-notes-write" {
  capabilities = ["read"]
}
