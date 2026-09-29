# ── modules/vpc ──────────────────────────────────────────────────────────────
# Required resources (Task B1). Only these belong in this module:
#
#   aws_vpc
#   aws_subnet                      public only in Lab 1
#   aws_internet_gateway
#   aws_route_table
#   aws_route_table_association
#   aws_security_group
#
# Name everything from var.project and var.environment. A hardcoded
# project-environment literal anywhere under modules/ fails the rubric grep.
#
# Example of the naming pattern expected:
#
#   resource "aws_vpc" "this" {
#     cidr_block = var.vpc_cidr
#     tags       = { Name = "${var.project}-${var.environment}-vpc" }
#   }

# TODO: implement the six resources above.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project}-${var.environment}-vpc"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidr
  map_public_ip_on_launch = true
  availability_zone       = var.availability_zone

  tags = {
    Name = "${var.project}-${var.environment}-public-1"
  }

}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags = {
    Name = "${var.project}-${var.environment}-igw"
  }

}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.project}-${var.environment}-public-rt"
  }

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

}

resource "aws_route_table_association" "this" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "this" {
  name        = "${var.project}-${var.environment}-sagemaker-sg"
  vpc_id      = aws_vpc.this.id
  description = "security group for lab1"
  ingress {
    description = "ALL traffic from within this VPC"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = [var.vpc_cidr]

  }
  egress {
    description = "ALL traffic from out of this VPC"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]

  }

  tags = {
    Name = "${var.project}-${var.environment}-sagemaker-sg"
  }
}

resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.private_subnet_cidr
  map_public_ip_on_launch = false
  availability_zone       = var.availability_zone

  tags = {
    Name = "${var.project}-${var.environment}-private-1"
  }
}

resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"
  tags   = { Name = "${var.project}-${var.environment}-eip" }
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public.id
  tags          = { Name = "${var.project}-${var.environment}-nat" }
}

# 1. The road-sign board for the private street (no routes inside yet)
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project}-${var.environment}-private-rt" }
}

# 2. The "everything else -> NAT" sign, only if the NAT exists

resource "aws_route" "private_nat" {
  count                  = var.enable_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

# 3. Put the board on the private street
resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}
