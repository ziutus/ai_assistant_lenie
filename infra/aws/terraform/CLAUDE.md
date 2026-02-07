# Terraform Infrastructure

Terraform configuration for provisioning AWS infrastructure for Project Lenie. This is one of three IaC approaches used in the project (alongside CloudFormation and CDK) for comparison purposes.

## Directory Structure

```
terraform/
├── main.tf                # Provider and Terraform version configuration
├── variables.tf           # Input variables
├── outputs.tf             # Output values (currently empty)
├── vpc.tf                 # VPC, subnets, route tables, internet gateway
├── ami.tf                 # Amazon Linux 2023 AMI data source
├── ssh_keys.tf            # SSH key pairs
├── ec2-nat-gateway.tf     # EC2 NAT gateway/bastion host module invocation
├── pvc_kubernetes.tf      # EKS VPC configuration (commented out, placeholder)
├── data/
│   └── ec2_nat_gateway.tpl  # User data template for bastion host
└── modules/
    └── ec2-nat-gateway/   # Reusable module for bastion/NAT gateway EC2
        ├── main.tf        # Security group + EC2 instance
        ├── variables.tf   # Module input variables
        └── outputs.tf     # Module outputs (currently empty)
```

## Provider Configuration

- **Terraform**: >= 1.0.0
- **AWS provider**: ~> 5.0
- **Region**: `us-east-1`
- **No remote backend configured** (local state)

## Input Variables

| Variable | Type | Description |
|----------|------|-------------|
| `project` | string | Project name (e.g. `lenie`) |
| `environment` | string | Environment name (`prod`, `dev`, `test`, etc.) |
| `vpc_cidr` | string | VPC CIDR block |
| `admin_ip` | string | Admin IP address for SSH access |
| `AWS_ACCOUNT_ID` | string | AWS account ID (default: `none`) |
| `AWS_ACCESS_KEY_ID` | string | AWS access key (default: `none`) |
| `AWS_SECRET_ACCESS_KEY` | string | AWS secret key (sensitive, default: `none`) |

## Resources

### VPC (`vpc.tf`)

- **VPC** with DNS hostnames and support enabled
- **2 public subnets** (auto-assigned public IP, in first 2 AZs)
- **2 private subnets** (no public IP, in first 2 AZs)
- **Internet Gateway** attached to VPC
- **Public route table** with default route to IGW
- **Private route table** (default VPC route table)
- Subnet CIDRs are dynamically calculated using `cidrsubnet()` from the VPC CIDR

Naming convention: `<project>-<environment>-<public|private>-<az>`

### AMI (`ami.tf`)

Data source that finds the latest Amazon Linux 2023 x86_64 HVM AMI from Amazon.

### SSH Keys (`ssh_keys.tf`)

Two key pairs:
- `ziutus_key` - RSA key (GitHub)
- `lenie_ai_key` - Ed25519 key (default Lenie key)

### EC2 NAT Gateway / Bastion Host (`ec2-nat-gateway.tf` + module)

Module `ec2-nat-gateway` creates:
- **Security group** with SSH (port 22) and ICMP ping from admin IP, all egress
- **EC2 instance** (`t2.micro`, 8GB root volume) in the first public subnet
- **User data** script that sets hostname and runs `yum update`

### Kubernetes VPC (`pvc_kubernetes.tf`)

Entirely commented out. Contains a placeholder for an EKS-compatible VPC using the `terraform-aws-modules/vpc/aws` module with:
- 3 private + 3 public subnets
- Single NAT gateway
- Kubernetes-specific tags for ELB integration

## Usage

```bash
# Initialize
terraform init

# Plan
terraform plan -var="project=lenie" -var="environment=dev" -var="vpc_cidr=10.0.0.0/16" -var="admin_ip=1.2.3.4"

# Apply
terraform apply -var="project=lenie" -var="environment=dev" -var="vpc_cidr=10.0.0.0/16" -var="admin_ip=1.2.3.4"

# Destroy
terraform destroy -var="project=lenie" -var="environment=dev" -var="vpc_cidr=10.0.0.0/16" -var="admin_ip=1.2.3.4"
```

Alternatively, create a `terraform.tfvars` file:
```hcl
project     = "lenie"
environment = "dev"
vpc_cidr    = "10.0.0.0/16"
admin_ip    = "1.2.3.4"
```

## Current State

This Terraform configuration covers a subset of the infrastructure (VPC + bastion host). The majority of AWS resources are currently managed via CloudFormation (`../cloudformation/`). The Terraform setup exists for comparison and learning purposes, as noted in the parent `infra/aws/CLAUDE.md`.
