# ── VPC ─────────────────────────────────────────────────────────────────────
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.project}-${var.environment}-vpc" }
}

# ── Internet Gateway ─────────────────────────────────────────────────────────
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project}-${var.environment}-igw" }
}

# ── Public Subnets (ALB, NAT Gateways) ──────────────────────────────────────
resource "aws_subnet" "public" {
  count = length(var.availability_zones)

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false # Only the ALB/NAT need internet; tasks use NAT

  tags = {
    Name = "${var.project}-${var.environment}-public-${count.index + 1}"
    Tier = "public"
  }
}

# ── Private Subnets (ECS tasks, RDS, ElastiCache, MSK) ──────────────────────
resource "aws_subnet" "private" {
  count = length(var.availability_zones)

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + length(var.availability_zones))
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "${var.project}-${var.environment}-private-${count.index + 1}"
    Tier = "private"
  }
}

# ── NAT Gateways (1 in dev, one-per-AZ in prod) ──────────────────────────────
resource "aws_eip" "nat" {
  count  = var.nat_gateway_count
  domain = "vpc"
  tags   = { Name = "${var.project}-${var.environment}-nat-eip-${count.index + 1}" }
}

resource "aws_nat_gateway" "main" {
  count = var.nat_gateway_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  depends_on    = [aws_internet_gateway.main]

  tags = { Name = "${var.project}-${var.environment}-nat-${count.index + 1}" }
}

# ── Route Tables ─────────────────────────────────────────────────────────────
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.project}-${var.environment}-rt-public" }
}

resource "aws_route_table_association" "public" {
  count          = length(var.availability_zones)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  # In dev: 1 NAT → 1 private RT reused across all AZs
  # In prod: 1 NAT per AZ → 1 private RT per AZ (no cross-AZ NAT traffic)
  count  = var.nat_gateway_count
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[count.index].id
  }

  tags = { Name = "${var.project}-${var.environment}-rt-private-${count.index + 1}" }
}

resource "aws_route_table_association" "private" {
  count     = var.nat_gateway_count > 0 ? length(var.availability_zones) : 0
  subnet_id = aws_subnet.private[count.index].id
  # Spread subnets across available NAT route tables (round-robin for dev)
  route_table_id = aws_route_table.private[count.index % var.nat_gateway_count].id
}

# LocalStack/MVP mode: no NAT gateway. Associate private subnets with the public
# route table so resources remain reachable in emulated environments.
resource "aws_route_table_association" "private_no_nat" {
  count          = var.nat_gateway_count == 0 ? length(var.availability_zones) : 0
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.public.id
}

# ── Security Groups ──────────────────────────────────────────────────────────

# ALB: internet-facing ingress on 80 + 443
resource "aws_security_group" "alb" {
  name        = "${var.project}-${var.environment}-sg-alb"
  description = "ALB: allow HTTP/HTTPS from internet"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.environment}-sg-alb" }
}

# App tier: only traffic from ALB on the app port
resource "aws_security_group" "app" {
  name        = "${var.project}-${var.environment}-sg-app"
  description = "ECS tasks: allow inbound from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Inbound from ALB (ingestor)"
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Inbound from ALB (dashboard)"
    from_port       = 8501
    to_port         = 8501
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.environment}-sg-app" }
}

# DB tier: only traffic from app tier on PostgreSQL port
resource "aws_security_group" "db" {
  name        = "${var.project}-${var.environment}-sg-db"
  description = "RDS: allow PostgreSQL from app tier only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from app tier"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-${var.environment}-sg-db" }
}

# Cache tier: only traffic from app tier on Redis port
resource "aws_security_group" "cache" {
  name        = "${var.project}-${var.environment}-sg-cache"
  description = "ElastiCache: allow Redis from app tier only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from app tier"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-${var.environment}-sg-cache" }
}

# MSK tier: only traffic from app tier on Kafka port
resource "aws_security_group" "msk" {
  name        = "${var.project}-${var.environment}-sg-msk"
  description = "MSK: allow Kafka from app tier only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Kafka TLS from app tier"
    from_port       = 9098
    to_port         = 9098
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-${var.environment}-sg-msk" }
}
