resource "aws_security_group" "public_sg" {
  name = "public_sg"
  description = "Security group for public access"
  vpc_id            = var.vpc_id
}

resource "aws_security_group_rule" "public_ssh_access" {
  type = "ingress"
  from_port = 22
  to_port = 22
  protocol = "tcp"
  security_group_id = aws_security_group.public_sg.id
  cidr_blocks = [var.admin_ip]
}

resource "aws_security_group_rule" "egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.public_sg.id
}

resource "aws_security_group_rule" "allow_ping" {
  type = "ingress"
  from_port = 8
  to_port = 0
  protocol = "icmp"
  security_group_id = aws_security_group.public_sg.id
  cidr_blocks = [var.admin_ip]
}

resource "aws_instance" "bastion_host" {
    instance_type = var.instance_type
    ami = var.ami
    key_name = var.ssh_key_name
    vpc_security_group_ids = [ aws_security_group.public_sg.id ]
    subnet_id = var.subnet_id
    root_block_device {
      volume_size = "8"
    }

    tags = {
          Name = var.name
    }

    user_data = templatefile("./data/ec2_nat_gateway.tpl", {new_hostname = "bastion-${var.environment}"})
}
