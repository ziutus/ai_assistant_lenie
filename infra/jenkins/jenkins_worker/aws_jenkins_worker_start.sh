#!/bin/bash

REGION="us-east-1"

TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
if [ -z "$TOKEN" ]; then
    echo "Failed to retrieve the token."
    exit 1
fi
IP_ADDRESS=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)

alternatives --set python3 /usr/bin/python3.11

aws ec2 authorize-security-group-ingress --region $REGION --group-id sg-086ad2b3e12e3f28d --protocol tcp --port 8443 --cidr ${IP_ADDRESS}/32

exit 0
