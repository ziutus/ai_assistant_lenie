locals {
  azs = data.aws_availability_zones.available.names
}

data "aws_availability_zones" "available" {}


resource "random_id" "random" {
  byte_length = 2
}


resource "aws_vpc" "lenie_vpc" {

  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
      Name = "${var.project}-${var.environment}-${random_id.random.dec}"
  }
  lifecycle  {
    create_before_destroy = true
  }
}

resource "aws_internet_gateway" "internet_gateway" {
  # vpc_id = module.vpc.vpc_id
  vpc_id = aws_vpc.lenie_vpc.id

  tags = {
    Name = "${var.project}_igw"
  }
}

resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.lenie_vpc.id

  tags = {
    Name = "${var.project}_public_rt"
  }
}

resource "aws_route" "default_route" {
  route_table_id = aws_route_table.public_rt.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id = aws_internet_gateway.internet_gateway.id
}

resource "aws_default_route_table" "private_rt" {
  default_route_table_id = aws_vpc.lenie_vpc.default_route_table_id
  tags = {
    Name = "${var.project}_private_rt"
  }
}

resource "aws_subnet" "subnet-public" {
  count = 2
  vpc_id            = aws_vpc.lenie_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone = local.azs[count.index]
  map_public_ip_on_launch = true

    tags = {
    Name = "${var.project}-${var.environment}-public-${local.azs[count.index]}"
  }
}

resource "aws_subnet" "subnet-private" {
  count = 2
  vpc_id            = aws_vpc.lenie_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, length(local.azs) + count.index)
  availability_zone = local.azs[count.index]
  map_public_ip_on_launch = false

    tags = {
    Name = "${var.project}-${var.environment}-private-${local.azs[count.index]}"
  }
}

resource "aws_route_table_association" "rt_public_assoc" {
  count = length(aws_subnet.subnet-public)
  subnet_id = aws_subnet.subnet-public.*.id[count.index]
  route_table_id = aws_route_table.public_rt.id
}

# Private route table is default, so below code is not needed
# resource "aws_route_table_association" "rt_private_assoc" {
#   count = length(aws_subnet.subnet-private)
#   subnet_id = aws_subnet.subnet-public[count.index].id
#   route_table_id = aws_route_table.public_rt.id
# }
