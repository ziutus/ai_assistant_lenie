variable "AWS_ACCOUNT_ID" {
  description = "The ID of the working account"
  type = string
  default = "none"
}

variable "AWS_SECRET_ACCESS_KEY" {
  type = string
  default = "none"
  sensitive = true
}

variable "AWS_ACCESS_KEY_ID" {
  type = string
  default = "none"
}
