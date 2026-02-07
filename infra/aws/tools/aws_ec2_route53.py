import boto3
import time


def start_ec2_instance(instance_id):
    """Start an EC2 instance and wait until it is running."""
    ec2 = boto3.client("ec2")
    print(f"Starting EC2 instance: {instance_id}")
    ec2.start_instances(InstanceIds=[instance_id])

    print("Waiting for instance to start...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    print("EC2 instance is running!")


def get_instance_public_ip(instance_id):
    """Get the public IP address of an EC2 instance, retrying if not yet available."""
    ec2 = boto3.client("ec2")
    print(f"Getting info for instance: {instance_id}")
    response = ec2.describe_instances(InstanceIds=[instance_id])

    public_ip = response["Reservations"][0]["Instances"][0].get("PublicIpAddress")
    if not public_ip:
        print("Public IP not yet available. Waiting...")
        time.sleep(10)
        return get_instance_public_ip(instance_id)

    print(f"Public IP: {public_ip}")
    return public_ip


def update_route53_record(hosted_zone_id, domain_name, public_ip):
    """Upsert a Route53 A record pointing to the given IP address."""
    route53 = boto3.client("route53")
    print(f"Updating Route53 A record for: {domain_name}")

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


def start_instance_and_update_dns(instance_id, hosted_zone_id, domain_name):
    """Start an EC2 instance, get its public IP, and update Route53 DNS."""
    start_ec2_instance(instance_id)
    public_ip = get_instance_public_ip(instance_id)
    update_route53_record(hosted_zone_id, domain_name, public_ip)
