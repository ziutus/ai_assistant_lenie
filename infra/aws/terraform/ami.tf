# aws ec2 describe-images --region us-east-1  --image-ids ami-05b10e08d247fb927
data "aws_ami" "al2023-ami" {
  most_recent = true
  owners      = ["amazon"] # Amazon images

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"] # Adjust for specific release or architecture
  }

  filter {
    name = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name = "architecture"
    values = ["x86_64"]
  }
}
