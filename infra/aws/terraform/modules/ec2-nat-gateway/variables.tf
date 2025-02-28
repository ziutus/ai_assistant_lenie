variable "instance_type" {
  type = string                     # The type of the variable, in this case a string
  description = "The type of EC2 instance" # Description of what this variable represents
}

variable "environment" {
  description = "Environment name (prod, dev, test etc)"
  type = string
}

variable "ami" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "admin_ip" {
  type = string
}

variable "name" {}

variable "ssh_key_name" {}

variable "subnet_id" {}
