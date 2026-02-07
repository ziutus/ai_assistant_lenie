# AWS Infrastructure for CI/CD

AWS-specific infrastructure patterns used by CI/CD pipelines: EC2 instance management, DNS updates, and CLI configuration.

> **Parent document:** [CI_CD.md](CI_CD.md) — general CI/CD pipeline rules and conventions.

## Automatic EC2 Instance Management

The pipeline automatically manages the AWS EC2 instance that serves as the runner:

**Starting instance (before pipeline):**
```bash
aws ec2 start-instances --instance-ids $INSTANCE_ID --region $AWS_REGION
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $AWS_REGION
```

**Stopping instance (after pipeline):**
```bash
aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $AWS_REGION
aws ec2 wait instance-stopped --instance-ids $INSTANCE_ID --region $AWS_REGION
```

## AWS CLI Configuration

```bash
aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
aws configure set region $AWS_REGION
```

## Scripts for Manually Starting Instances with DNS Update

When shutting down AWS infrastructure to save costs, after restarting the EC2 instance, its public IP changes. The following pattern automatically updates the DNS record in Route 53.

**Python script pattern (`ec2_start_with_dns.py`):**

```python
import boto3
import time
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration from .env file
INSTANCE_ID = os.getenv("AWS_INSTANCE_ID")
HOSTED_ZONE_ID = os.getenv("AWS_HOSTED_ZONE_ID")
DOMAIN_NAME = os.getenv("DOMAIN_NAME")


def start_ec2_instance(instance_id):
    """Starts the EC2 instance"""
    ec2 = boto3.client("ec2")
    print(f"Starting EC2 instance with ID: {instance_id}")
    ec2.start_instances(InstanceIds=[instance_id])

    print("Waiting for instance to start...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print("EC2 instance has been started!")


def get_instance_public_ip(instance_id):
    """Gets the public IP address of the EC2 instance"""
    ec2 = boto3.client("ec2")
    response = ec2.describe_instances(InstanceIds=[instance_id])

    public_ip = response["Reservations"][0]["Instances"][0].get("PublicIpAddress")
    if not public_ip:
        print("Public IP address is not yet available. Waiting...")
        time.sleep(10)
        return get_instance_public_ip(instance_id)

    print(f"Instance public IP address: {public_ip}")
    return public_ip


def update_route53_record(hosted_zone_id, domain_name, public_ip):
    """Updates the A record in Route 53"""
    route53 = boto3.client("route53")
    print(f"Updating A record in Route 53 for domain: {domain_name}")

    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            "Changes": [
                {
                    "Action": "UPSERT",
                    "ResourceRecordSet": {
                        "Name": domain_name,
                        "Type": "A",
                        "TTL": 300,
                        "ResourceRecords": [{"Value": public_ip}],
                    },
                }
            ]
        },
    )
    print(f"A record updated! Status: {response['ChangeInfo']['Status']}")


if __name__ == "__main__":
    if not all([INSTANCE_ID, HOSTED_ZONE_ID, DOMAIN_NAME]):
        raise ValueError("Set INSTANCE_ID, HOSTED_ZONE_ID, and DOMAIN_NAME variables in .env")

    # 1. Start EC2 instance
    start_ec2_instance(INSTANCE_ID)

    # 2. Get public IP address
    public_ip = get_instance_public_ip(INSTANCE_ID)

    # 3. Update Route 53 record
    update_route53_record(HOSTED_ZONE_ID, DOMAIN_NAME, public_ip)
```

**Required variables in `.env`:**

```bash
# For Jenkins
JENKINS_AWS_INSTANCE_ID=i-0123456789abcdef0
JENKINS_DOMAIN_NAME=jenkins.example.com

# For OpenVPN
OPENVPN_OWN_AWS_INSTANCE_ID=i-0987654321fedcba0
OPENVPN_OWN_DOMAIN_NAME=vpn.example.com

# Common
AWS_HOSTED_ZONE_ID=Z0123456789ABCDEFGHIJ
```

**Required IAM permissions:**

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:StartInstances",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "route53:ChangeResourceRecordSets"
            ],
            "Resource": "arn:aws:route53:::hostedzone/HOSTED_ZONE_ID"
        }
    ]
}
```

**Usage:**

```bash
# Install dependencies
pip install boto3 python-dotenv

# Run
python ec2_start_with_dns.py
```

> **Note:** The actual implementation is in `infra/aws/tools/aws_ec2_route53.py` and can be invoked via `make aws-start-openvpn`. The script above is a reference pattern for CI/CD documentation purposes.
