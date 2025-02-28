module "ec2-nat-gateway" {
  source = "./modules/ec2-nat-gateway"
  vpc_id = aws_vpc.lenie_vpc.id
  subnet_id = aws_subnet.subnet-public[0].id
  environment = var.environment
  admin_ip = "${var.admin_ip}/32"
  ami = data.aws_ami.al2023-ami.id
  name = "${var.project}-${lower(var.environment)}-nat-gateway"
  instance_type = "t2.micro"
  ssh_key_name = aws_key_pair.lenie_ai_key.id
}
