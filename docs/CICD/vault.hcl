storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1
}

seal "awskms" {
  region     = "eu-central-1"
  kms_key_id = "0c6a400d-096b-4b9c-9098-7a0ec7a74f15"
}

ui = true
disable_mlock = true
api_addr = "http://0.0.0.0:8200"
