import os
from dotenv import load_dotenv
from aws_ec2_route53 import start_instance_and_update_dns

load_dotenv()

INSTANCE_ID = os.getenv("JENKINS_AWS_INSTANCE_ID")
HOSTED_ZONE_ID = os.getenv("AWS_HOSTED_ZONE_ID")
DOMAIN_NAME = os.getenv("JENKINS_DOMAIN_NAME")

if __name__ == "__main__":
    if not all([INSTANCE_ID, HOSTED_ZONE_ID, DOMAIN_NAME]):
        raise ValueError(
            "Make sure JENKINS_AWS_INSTANCE_ID, AWS_HOSTED_ZONE_ID and JENKINS_DOMAIN_NAME are set in .env")

    start_instance_and_update_dns(INSTANCE_ID, HOSTED_ZONE_ID, DOMAIN_NAME)
