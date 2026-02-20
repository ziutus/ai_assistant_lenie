# Self-hosted Jenkins on EC2

> **Note:** Jenkins is currently not in use. The `aws-start-jenkins` Makefile target has been removed.
> To restore it, add the following to the root `Makefile` (in the AWS operations section):
>
> ```makefile
> aws-start-jenkins:  ## Start Jenkins EC2 and update Route53 DNS
> 	python infra/aws/tools/aws_ec2_route53.py --instance-id $(JENKINS_AWS_INSTANCE_ID) --hosted-zone-id $(AWS_HOSTED_ZONE_ID) --domain-name $(JENKINS_DOMAIN_NAME)
> ```
>
> Required `.env` variables: `JENKINS_AWS_INSTANCE_ID`, `AWS_HOSTED_ZONE_ID`, `JENKINS_DOMAIN_NAME`

> **Archived Lambda:** The `jenkins-job-start` Lambda function (triggered Jenkins jobs via HTTP API with CSRF crumb auth) has been archived and removed from the codebase. Code is preserved in git tag `archive/jenkins-job-start`.
> Restore with:
> ```bash
> git checkout archive/jenkins-job-start -- infra/aws/serverless/lambdas/jenkins-job-start/
> ```

> **Parent document:** [CI_CD.md](CI_CD.md) — general CI/CD pipeline rules and conventions.

## Automatic Security Group Configuration at Startup

Script run at EC2 instance startup that automatically adds the worker's public IP to the Jenkins Security Group, enabling connection.

**Startup script (`/usr/local/bin/aws_jenkins_worker_start.sh`):**

```bash
#!/bin/bash

REGION="us-east-1"

# Get IMDSv2 token
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

if [ -z "$TOKEN" ]; then
    echo "Failed to retrieve the token."
    exit 1
fi

# Get instance public IP
IP_ADDRESS=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
    http://169.254.169.254/latest/meta-data/public-ipv4)

# Set Python 3.11 as default
alternatives --set python3 /usr/bin/python3.11

# Add rule to Security Group
aws ec2 authorize-security-group-ingress \
    --region $REGION \
    --group-id sg-XXXXXXXXX \
    --protocol tcp \
    --port 8443 \
    --cidr ${IP_ADDRESS}/32

exit 0
```

**Notes:**
- Uses IMDSv2 (Instance Metadata Service v2) for security
- Requires IAM permissions: `ec2:AuthorizeSecurityGroupIngress`
- Change `sg-XXXXXXXXX` to your Security Group ID

**Systemd file (`/etc/systemd/system/jenkins_worker.service`):**

```ini
[Unit]
Description=Update AWS Security Group for Jenkins Server to allow connection
After=network.target

[Service]
ExecStart=/usr/local/bin/aws_jenkins_worker_start.sh
Type=simple
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
```

**Service installation:**

```bash
# Copy script
sudo cp aws_jenkins_worker_start.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/aws_jenkins_worker_start.sh

# Copy service file
sudo cp jenkins_worker.service /etc/systemd/system/

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable jenkins_worker.service
sudo systemctl start jenkins_worker.service
```

## SSL Certificates (Let's Encrypt)

Jenkins can use SSL certificates from Let's Encrypt.

**Certificate renewal:**

```bash
letsencrypt renew
```

**Conversion to PKCS12 format:**

```bash
openssl pkcs12 -export \
    -in /etc/letsencrypt/live/jenkins.example.com/fullchain.pem \
    -inkey /etc/letsencrypt/live/jenkins.example.com/privkey.pem \
    -out jenkins.p12 \
    -name jenkins \
    -CAfile /etc/letsencrypt/live/jenkins.example.com/chain.pem \
    -caname root
```

**Import to Java KeyStore:**

```bash
keytool -importkeystore \
    -deststorepass <keystore_password> \
    -destkeypass <key_password> \
    -destkeystore /var/lib/jenkins/jenkins.jks \
    -srckeystore jenkins.p12 \
    -srcstoretype PKCS12 \
    -srcstorepass <p12_password> \
    -alias jenkins
```

## GitHub Webhooks

> **Note:** The `/infra/git-webhooks` API Gateway endpoint and its `git-webhooks` Lambda function have been removed (Sprint 4, Story 14.2). The Lambda is archived under git tag `archive/git-webhooks`. Jenkins is no longer in use, so the webhook integration is not needed.

## Code Checkout

```groovy
git credentialsId: 'github-token',
    url: 'https://github.com/ziutus/ai_assistant_lenie_server',
    branch: "${env.BRANCH_NAME}"
```

## Checking EC2 Instance State

```bash
aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --query "Reservations[0].Instances[0].State.Name" \
    --output text \
    --region $AWS_REGION
```

## Archiving Artifacts

```groovy
archiveArtifacts artifacts: 'results/semgrep-report.json', fingerprint: true
archiveArtifacts artifacts: 'pytest-results/**/*', allowEmptyArchive: true
```

## Parallel Execution

```groovy
stage('Python tests') {
    parallel {
        stage('Run Pytest') { ... }
        stage('Run Flake8 Style Check') { ... }
    }
}
```
