ui = true

disable_mlock = false

storage "raft" {
  path    = "/openbao/data"
  node_id = "jason-openbao-1"
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  tls_disable     = true
}

api_addr     = "http://127.0.0.1:8200"
cluster_addr = "http://127.0.0.1:8201"

log_level = "info"
