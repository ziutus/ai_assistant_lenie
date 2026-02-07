# CI/CD Reference Documentation

This document serves as a **knowledge base for the AI agent** for creating new CI/CD pipelines. It contains proven patterns, commands, and configurations gathered from previous implementations (GitLab CI, Jenkins, CircleCI).

> **Note:** This document does not describe an active pipeline. It serves as a reference for building new CI/CD configurations.

## Project Context

**Hobby project** - infrastructure does not run 24/7. Virtual machines are started only when needed to reduce costs.

**Dynamic IP addresses** - to save costs, IP addresses are not reserved (Elastic IP) but assigned dynamically when instances start. Therefore, startup scripts include DNS record updates (e.g., Route 53).

**Self-hosted runners** - to reduce costs, pipelines use self-hosted runners instead of those provided by CI/CD vendors (e.g., CircleCI, GitLab). This allows leveraging the AWS or Google Cloud free tier for compute resources, rather than paying for CI/CD provider's build minutes.

**History and development direction:**
- **Beginnings (AWS)** - the project was originally created as serverless on AWS to explore the platform's capabilities
- **Current direction (GCP)** - the author works professionally with Google Cloud Platform, so the project will be migrated to GCP
- **Kubernetes** - Kubernetes deployment option is supported due to the desire to deepen knowledge in this area

## Document Purpose

The AI agent should use this documentation to:
- Create new CI/CD pipelines for any platform
- Select appropriate security and testing tools
- Configure AWS infrastructure (EC2 runner)
- Implement Docker builds and deployment

## Table of Contents

1. [Project Context](#project-context)
2. [Pipeline Overview](#pipeline-overview)
3. [CircleCI Pattern](#circleci-pattern)
4. [AWS Infrastructure](#aws-infrastructure)
   - [Scripts for Starting Instances with DNS Update](#scripts-for-manually-starting-instances-with-dns-update)
5. [Preparing Self-hosted EC2 Runner](#preparing-self-hosted-ec2-runner)
6. [Self-hosted Jenkins on EC2](#self-hosted-jenkins-on-ec2)
7. [Pipeline Stages](#pipeline-stages)
8. [Security Tools](#security-tools)
   - [Semgrep](#semgrep---static-code-analysis)
   - [TruffleHog](#trufflehog---secret-detection)
   - [OSV Scanner](#osv-scanner---dependency-vulnerability-scanning)
   - [Qodana](#qodana---jetbrains-code-analysis)
9. [Tests and Code Quality](#tests-and-code-quality)
10. [Docker Build and Deploy](#docker-build-and-deploy)
11. [Environment Variables](#environment-variables)
12. [Artifacts](#artifacts)

---

## Pipeline Overview

The CI/CD pipeline consists of the following main stages:

```
.pre (start_runner)
    ↓
test + security-checks (parallel)
    ↓
build
    ↓
deploy
    ↓
clean-node
    ↓
.post (stop_runner)
```

## CircleCI Pattern

Example CircleCI configuration with a self-hosted runner on EC2.

### Architecture

```
start-ec2
    ↓
run-job-on-ec2 (tests)
    ↓
run-job-on-ec2-docker (build)
    ↓
stop-ec2
```

### Orbs and Executors

```yaml
orbs:
  aws-cli: circleci/aws-cli@3.1    # AWS CLI integration

executors:
  python-executor:                  # Lightweight Python container
    docker:
      - image: cimg/python:3.11

  machine-executor:                 # Machine with Docker
    machine:
      docker_layer_caching: true    # Docker layer cache
```

### Jobs

#### 1. start-ec2
Starts the EC2 instance before running tests.

```yaml
jobs:
  start-ec2:
    executor: python-executor
    steps:
      - aws-cli/setup
      - run:
          name: "Start EC2 instances"
          command: |
            aws ec2 start-instances --instance-ids $INSTANCE_ID
```

#### 2. run-job-on-ec2
Installs dependencies and runs tests on the self-hosted EC2 runner.

```yaml
run-job-on-ec2:
  executor: machine-executor
  resource_class: itsnap/itsnap-runner    # Self-hosted runner
  steps:
    - checkout
    - run:
        name: "Install uv and dependencies"
        command: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          export PATH="$HOME/.cargo/bin:$PATH"
          uv venv venv
          . venv/bin/activate
          uv pip install -r backend/requirements_server.txt
    - run:
        name: "Run tests"
        command: |
          . venv/bin/activate
          mkdir -p test-results
          python -m pytest tests/unit --junitxml=test-results/results.xml || true
    - store_test_results:
        path: test-results/results.xml
```

**Notes:**
- Uses `uv venv` instead of `--system` (isolated environment)
- Generates report in JUnit XML format
- Unit tests only (`tests/unit`)

#### 3. run-job-on-ec2-docker
Builds Docker image on the self-hosted runner.

```yaml
run-job-on-ec2-docker:
  executor: machine-executor
  resource_class: itsnap/itsnap-runner
  steps:
    - checkout
    - run:
        name: "Execute job on EC2"
        command: |
          docker build -t lenie-ai-server:latest .
```

#### 4. stop-ec2
Stops the EC2 instance after the pipeline completes.

```yaml
stop-ec2:
  executor: python-executor
  steps:
    - aws-cli/setup
    - run:
        name: "Stop EC2 instances"
        command: |
          aws ec2 stop-instances --instance-ids $INSTANCE_ID
```

### Workflow

```yaml
workflows:
  ec2-workflow:
    jobs:
      - start-ec2:
          filters:
            branches:
              only: [main, dev]
      - run-job-on-ec2:
          requires: [start-ec2]
          filters:
            branches:
              only: [main, dev]
      - run-job-on-ec2-docker:
          requires: [run-job-on-ec2]
          filters:
            branches:
              only: [main, dev]
      - stop-ec2:
          requires: [run-job-on-ec2-docker]
          filters:
            branches:
              only: [main, dev]
```

### Self-hosted Runner

CircleCI uses a self-hosted runner on EC2:
- **Resource class:** `itsnap/itsnap-runner`
- Runner must be installed on the EC2 instance
- Documentation: https://circleci.com/docs/runner-overview/

### Storing Test Results

```yaml
- store_test_results:
    path: test-results/results.xml
```

CircleCI automatically parses JUnit XML format and displays results in the UI.

## AWS Infrastructure

### Automatic EC2 Instance Management

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

**Checking instance state (Jenkins):**
```bash
aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --query "Reservations[0].Instances[0].State.Name" \
    --output text \
    --region $AWS_REGION
```

### AWS CLI Configuration

```bash
aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
aws configure set region $AWS_REGION
```

### Scripts for Manually Starting Instances with DNS Update

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

## Preparing Self-hosted EC2 Runner

Instructions for preparing an EC2 instance as a self-hosted CI/CD runner (Amazon Linux 2023).

### 1. Installing Python 3.11

The project requires Python 3.11. Installation and setting as default version:

```bash
# Install Python 3.11 (if not installed)
sudo dnf install python3.11 -y

# Set Python 3.11 as default
sudo alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
sudo alternatives --config python3

# Verification
python3 --version
# Python 3.11.6
```

### 2. Installing pip

```bash
sudo dnf install python3-pip -y
```

### 3. Installing Go (for osv-scanner)

```bash
sudo dnf update -y
sudo dnf install -y golang

# Verification
go version
```

### 4. Installing Testing Tools

**Flake8 with HTML reports:**
```bash
pip3 install flake8-html
```

**Pytest with HTML reports:**
```bash
pip3 install pytest-html
```

### 5. Installing Security Tools

**Semgrep:**
```bash
python3 -m pip install semgrep

# If there are dependency conflicts:
python3 -m pip install --ignore-installed semgrep
```

**OSV Scanner (via Go):**
```bash
go install github.com/google/osv-scanner/cmd/osv-scanner@v1

# Binary will be installed in ~/go/bin/
# Add to PATH or copy to /usr/local/bin/
sudo cp ~/go/bin/osv-scanner /usr/local/bin/
```

### 6. Installing Docker (optional)

```bash
sudo dnf install docker -y
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group
sudo usermod -aG docker $USER
```

### 7. Installing uv (fast package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"
```

### Summary of Installed Tools

| Tool | Command | Description |
|------|---------|-------------|
| Python 3.11 | `python3` | Python interpreter |
| pip | `pip3` | Python package manager |
| Go | `go` | Go compiler |
| Flake8 | `flake8` | Code style linter |
| Pytest | `pytest` | Testing framework |
| Semgrep | `semgrep` | Security static analysis |
| OSV Scanner | `osv-scanner` | Vulnerability scanning |
| Docker | `docker` | Containerization |
| uv | `uv` | Fast Python package manager |

## Self-hosted Jenkins on EC2

> **Note:** Jenkins is currently not in use. The `aws-start-jenkins` Makefile target has been removed.
> To restore it, add the following to the root `Makefile` (in the AWS operations section):
>
> ```makefile
> aws-start-jenkins:  ## Start Jenkins EC2 and update Route53 DNS
> 	python infra/aws/tools/aws_ec2_route53.py --instance-id $(JENKINS_AWS_INSTANCE_ID) --hosted-zone-id $(AWS_HOSTED_ZONE_ID) --domain-name $(JENKINS_DOMAIN_NAME)
> ```
>
> Required `.env` variables: `JENKINS_AWS_INSTANCE_ID`, `AWS_HOSTED_ZONE_ID`, `JENKINS_DOMAIN_NAME`

Additional configurations for self-hosted Jenkins on an EC2 instance.

### Automatic Security Group Configuration at Startup

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

### SSL Certificates (Let's Encrypt)

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

### GitHub Webhooks

Testing GitHub webhooks:

```bash
curl -X POST \
    -H "Content-Type: application/json" \
    -d '{"key1":"value1", "key2":"value2"}' \
    https://your-api-gateway.execute-api.us-east-1.amazonaws.com/v1/infra/git-webhooks
```

## Pipeline Stages

### 1. Environment Preparation

**Installing uv (fast Python package manager):**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"
```

**Installing dependencies:**
```bash
uv pip install --system -r backend/requirements_server.txt
```

### 2. Code Checkout

**Jenkins (from GitHub):**
```groovy
git credentialsId: 'github-token',
    url: 'https://github.com/ziutus/ai_assistant_lenie_server',
    branch: "${env.BRANCH_NAME}"
```

### 3. Creating Report Directories

```bash
mkdir -p results/
mkdir -p pytest-results/
mkdir -p flake_reports/
```

## Security Tools

### Local Development - Quick Security Checks

For local development, all security tools can be run via `uvx` (uv tool runner) without installing to project venv:

```bash
make security        # Semgrep static analysis
make security-deps   # pip-audit - dependency vulnerabilities
make security-bandit # Bandit - Python security linter
make security-safety # Safety - dependency check
make security-all    # Run all checks
```

| Tool | Command | Purpose |
|------|---------|---------|
| Semgrep | `uvx semgrep --config=auto backend/` | Static code analysis |
| pip-audit | `uvx pip-audit` | PyPI advisory database check |
| Bandit | `uvx bandit -r backend/` | Python security linter |
| Safety | `uvx safety scan` | Dependency vulnerability check (requires free account) |

### Semgrep - Static Code Analysis

Semgrep detects potential security vulnerabilities in code.

```bash
# CI - Installation and run
uv pip install --system semgrep
semgrep --config=auto --output semgrep-report.json
```

**Local development:** Use `uvx` to run semgrep without installing to project venv:
```bash
make security
# or directly:
uvx semgrep --config=auto backend/
```

**Artifact:** `semgrep-report.json`

### TruffleHog - Secret Detection

TruffleHog scans the repository for accidentally committed secrets (API keys, passwords, tokens).

```bash
docker run --rm --name trufflehog \
    trufflesecurity/trufflehog:latest git file://. \
    --only-verified --bare 2>&1 | tee trufflehog.txt
```

**Flags:**
- `--only-verified` - reports only verified secrets
- `--bare` - minimalistic output

**Artifact:** `trufflehog.txt`

### OSV Scanner - Dependency Vulnerability Scanning

OSV Scanner checks dependencies for known vulnerabilities.

```bash
/usr/local/bin/osv-scanner scan --lockfile requirements.txt
```

**Note:** This stage may require additional configuration.

**Artifact:** `osv_scan_results.json`

### Qodana - JetBrains Code Analysis

Qodana is a JetBrains tool for static code analysis, integrating inspections from PyCharm/IntelliJ.

#### Configuration (`qodana.yaml`)

```yaml
version: "1.0"
profile:
  name: qodana.starter           # Inspection profile (starter/recommended/all)
linter: jetbrains/qodana-python:latest  # Python linter

# Optional - enable/disable inspections
# include:
#   - name: PyUnusedLocalInspection
# exclude:
#   - name: PyBroadExceptionInspection
#     paths:
#       - legacy/
```

#### Running in CI/CD

**GitLab CI:**
```yaml
image: jetbrains/qodana-python-community:2024.1
cache:
  key: qodana-2024.1-$CI_DEFAULT_BRANCH-$CI_COMMIT_REF_SLUG
  paths:
    - .qodana/cache
variables:
  QODANA_TOKEN: $QODANA_TOKEN
  QODANA_ENDPOINT: "https://qodana.cloud"
script:
  - qodana --cache-dir=$CI_PROJECT_DIR/.qodana/cache
```

**Locally (Docker):**
```bash
docker run --rm -it \
  -v $(pwd):/data/project/ \
  -v $(pwd)/.qodana:/data/results/ \
  jetbrains/qodana-python:latest
```

#### Detected Issues (Python Inspections)

| Inspection | Description | Priority |
|------------|-------------|----------|
| `PyArgumentListInspection` | Missing/extra function arguments | WARNING |
| `PyBroadExceptionInspection` | Too broad exception catching (`except Exception`) | WARNING |
| `PyDefaultArgumentInspection` | Mutable default argument (e.g., `def f(x=[])`) | WARNING |
| `PyTypeCheckerInspection` | Type mismatch (type hints) | WARNING |
| `PyUnusedLocalInspection` | Unused local variables | WARNING |
| `PyUnresolvedReferencesInspection` | Unresolved references/imports | ERROR |

#### SARIF Report Format

Qodana generates a report in SARIF format (Static Analysis Results Interchange Format):

```json
{
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "PY",
        "fullName": "Qodana",
        "version": "242.23726.102"
      }
    },
    "results": [{
      "ruleId": "PyArgumentListInspection",
      "level": "warning",
      "message": { "text": "Parameter 'stack' unfilled" },
      "locations": [{
        "physicalLocation": {
          "artifactLocation": { "uri": "library/api/aws/s3_aws.py" },
          "region": { "startLine": 30, "startColumn": 39 }
        }
      }]
    }]
  }]
}
```

**Artifacts:**
- `qodana.sarif.json` - detailed results report
- `.qodana/` - cache and additional reports

**Requires:** `QODANA_TOKEN` token and qodana.cloud account (optional for local use)

## Tests and Code Quality

### Pytest - Unit and Integration Tests

```bash
# Run with HTML report
pytest --self-contained-html --html=pytest-results/report.html
```

**Flags:**
- `--self-contained-html` - generates a standalone HTML file (without external resources)
- `--html=pytest-results/report.html` - path to report

**Artifact:** `pytest-results/` (entire directory)

### Flake8 - Code Style Checking

```bash
# Installation
uv pip install --system flake8-html

# Run with HTML report
flake8 --format=html --htmldir=flake_reports/

# With directory exclusion
flake8 --format=html --exclude=ai_dev3 --htmldir=flake_reports/
```

**Artifact:** `flake_reports/` (entire directory)

## Docker Build and Deploy

### Building Docker Image

```bash
# Build with version tag
docker build -t $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$TAG_VERSION .

# Tag as latest
docker tag $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$TAG_VERSION \
           $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:latest
```

### Push to Docker Hub

```bash
# Login
docker login -u "$DOCKER_HUB_USERNAME" -p "$DOCKER_HUB_TOKEN"

# Push both tags
docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$TAG_VERSION
docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:latest
```

### Cleaning Old Images

```bash
chmod +x infra/docker/docker_images_clean.sh
infra/docker/docker_images_clean.sh --remove-name lenie
```

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `us-east-1` |
| `INSTANCE_ID` | EC2 runner instance ID | `i-03908d34c63fce042` |
| `CI_REGISTRY_IMAGE` | Docker image name | `lenie-ai-server` |
| `TAG_VERSION` | Docker tag version | `0.2.11.6` |

### Secrets (stored in CI/CD)

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS access key (GitLab: `GITLAB_AWS_ACCESS_KEY_ID`) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (GitLab: `GITLAB_AWS_SECRET_ACCESS_KEY`) |
| `DOCKER_HUB_USERNAME` | Docker Hub username |
| `DOCKER_HUB_TOKEN` | Docker Hub access token |
| `QODANA_TOKEN` | Qodana token (optional) |

## Artifacts

### List of Artifacts Generated by the Pipeline

| Artifact | Stage | Description |
|----------|-------|-------------|
| `semgrep-report.json` | security-checks | Semgrep static analysis report |
| `trufflehog.txt` | security-checks | Detected secrets report |
| `osv_scan_results.json` | security-checks | Dependency vulnerability report |
| `qodana.sarif.json` | security-checks | Qodana report in SARIF format |
| `pytest-results/` | test | Pytest test reports (HTML) |
| `flake_reports/` | test | Flake8 code style reports (HTML) |

### Archiving Artifacts (Jenkins)

```groovy
archiveArtifacts artifacts: 'results/semgrep-report.json', fingerprint: true
archiveArtifacts artifacts: 'pytest-results/**/*', allowEmptyArchive: true
```

## Pipeline Triggers

The pipeline runs for branches:
- `dev`
- `main`

Build and deploy stages execute only for these branches.

## Parallel Execution

Some stages can be executed in parallel:

**GitLab CI:**
- `job-pytest` and `job-style-tool-flake8-scan` (stage: test)
- `job-security-tool-semgrep`, `job-security-tool-trufflehog`, `job-security-tool-osv_scan` (stage: security-checks)

**Jenkins:**
```groovy
stage('Python tests') {
    parallel {
        stage('Run Pytest') { ... }
        stage('Run Flake8 Style Check') { ... }
    }
}
```

---

## How to Use This Documentation

When creating a new CI/CD pipeline:

1. **Choose a platform** (GitHub Actions, GitLab CI, CircleCI, Jenkins, etc.)
2. **Define stages** - use [Pipeline Overview](#pipeline-overview) as a template
3. **Configure infrastructure** - if using a self-hosted runner, see [AWS Infrastructure](#aws-infrastructure)
4. **Add security tools** - choose from [Security Tools](#security-tools) section
5. **Configure tests** - see [Tests and Code Quality](#tests-and-code-quality)
6. **Set variables** - list in [Environment Variables](#environment-variables)

---

*Reference documentation generated from historical configurations: CircleCI, GitLab CI, Jenkins (worker scripts, SSL), Qodana, README_RUNNER.md*
