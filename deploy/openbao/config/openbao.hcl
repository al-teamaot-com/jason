ui = true

storage "raft" {
  path    = "/openbao/data"
  node_id = "jason-openbao-01"
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_disable     = true
}

api_addr     = "http://openbao:8200"
cluster_addr = "http://openbao:8201"

disable_mlock = true

audit "file" "jason-file" {
  description = "Persistent Jason OpenBao audit log"

  options {
    file_path = "/openbao/audit/audit.log"
    mode      = "0600"
    log_raw   = "false"
  }
}
