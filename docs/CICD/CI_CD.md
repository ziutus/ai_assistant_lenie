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
2. [Target Pipeline Specification](#target-pipeline-specification)
3. [Platform-specific Patterns](#platform-specific-patterns)
4. [AWS Infrastructure](#aws-infrastructure) → [AWS_Infrastructure.md](AWS_Infrastructure.md)
5. [Preparing Self-hosted EC2 Runner](#preparing-self-hosted-ec2-runner) → [AWS_EC2_Runner_Setup.md](AWS_EC2_Runner_Setup.md)
6. [Self-hosted Jenkins on EC2](#self-hosted-jenkins-on-ec2) → [Jenkins.md](Jenkins.md)
7. [Tools Reference](#tools-reference) → [CI_CD_Tools.md](CI_CD_Tools.md)
8. [Environment Variables](#environment-variables)
9. [Artifacts](#artifacts)

---

## Target Pipeline Specification

This section defines the **canonical pipeline** that should be implemented on any CI/CD platform. When generating a new pipeline configuration, follow this specification and adapt it to the platform's syntax.

### Pipeline Flow

```
1. INFRA-START        Start self-hosted runner (EC2)
       ↓
2. VALIDATE           Version validation (only for releases to main)
       ↓
3. TEST               Unit tests + code style checks + Helm lint     ← parallel
   SECURITY-CODE      Static analysis + secret detection + dep scan  ← parallel
       ↓
4. BUILD-DOCKER       Build Docker image, tag with version + latest
       ↓
5. SECURITY-DOCKER    Scan built Docker image for vulnerabilities
   BUILD-HELM         Package Helm chart with correct version        ← parallel
       ↓
6. DEPLOY             Push Docker image to registry + publish Helm chart to S3
       ↓
7. CLEANUP            Remove old Docker images from runner
       ↓
8. INFRA-STOP         Stop self-hosted runner (EC2)
```

### Stage 1: INFRA-START

**Purpose:** Start the self-hosted EC2 runner to save costs (instance runs only during pipeline).

| Parameter | Value |
|-----------|-------|
| AWS Region | `us-east-1` |
| Instance ID | `$INSTANCE_ID` (CI/CD variable) |
| Requires | AWS CLI, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Git checkout | Not needed (`GIT_STRATEGY: none`) |

**Command:**
```bash
aws ec2 start-instances --instance-ids $INSTANCE_ID
```

### Stage 2: VALIDATE

**Purpose:** Ensure releases to `main` have a valid, incrementing semver version.

**Trigger:** Only on merge/pull requests targeting `main`.

**Logic:**
1. Check that the MR/PR has a label/tag matching `^[0-9]+\.[0-9]+\.[0-9]+$`
2. Fetch all existing git tags
3. Verify that the new version is strictly greater than the latest existing tag
4. Export `NEW_VERSION` for downstream stages

**Output:** `NEW_VERSION` environment variable (via dotenv artifact or equivalent).

### Stage 3: TEST + SECURITY-CODE (parallel)

All jobs in this stage run in **parallel** on the self-hosted runner.

#### 3a. Unit Tests (pytest)

| Parameter | Value |
|-----------|-------|
| Dependencies | `uv sync` or `pip install -r requirements.txt` |
| Command | `pytest --self-contained-html --html=pytest-results/` |
| Report format | HTML (self-contained) |
| Artifact | `pytest-results/` |
| Failure policy | Non-blocking (`|| true`) during development |

#### 3b. Code Style (flake8)

| Parameter | Value |
|-----------|-------|
| Dependencies | `flake8-html` |
| Command | `flake8 --format=html --htmldir=flake_reports/` |
| Artifact | `flake_reports/` |

#### 3c. Helm Lint

| Parameter | Value |
|-----------|-------|
| Command | `helm lint infra/kubernetes/lenie/helm/lenie-ai-server` |
| Condition | Only if Helm charts exist |

#### 3d. Semgrep (SAST)

| Parameter | Value |
|-----------|-------|
| Command | `semgrep --config=auto --output semgrep-report.json` |
| Artifact | `semgrep-report.json` |

#### 3e. TruffleHog (secret detection)

| Parameter | Value |
|-----------|-------|
| Command | `docker run --rm trufflesecurity/trufflehog:latest git file://. --only-verified --bare` |
| Artifact | `trufflehog.txt` |

#### 3f. OSV Scanner (dependency vulnerabilities)

| Parameter | Value |
|-----------|-------|
| Command | `osv-scanner scan --lockfile requirements.txt` |
| Artifact | `osv_scan_results.json` |

#### 3g. Qodana (optional, JetBrains static analysis)

| Parameter | Value |
|-----------|-------|
| Image | `jetbrains/qodana-python-community:2024.1` |
| Command | `qodana --cache-dir=$CI_PROJECT_DIR/.qodana/cache` |
| Requires | `QODANA_TOKEN` |
| Status | Optional — disabled by default |

### Stage 4: BUILD-DOCKER

**Purpose:** Build Docker image for the backend server.

| Parameter | Value |
|-----------|-------|
| Image name | `$DOCKER_HUB_USERNAME/lenie-ai-server` |
| Version tag | `$NEW_VERSION` (from VALIDATE) or fallback `$TAG_VERSION` |
| Additional tag | `latest` |
| Depends on | VALIDATE stage |
| Trigger | MR to `main`, or push to `dev`/`main` |

**Commands:**
```bash
docker build -t $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$VERSION .
docker tag $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$VERSION $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:latest
```

**Output:** `VERSION` and `HELM_VERSION` environment variables for downstream stages.

### Stage 5: SECURITY-DOCKER + BUILD-HELM (parallel)

#### 5a. Trivy (Docker image scan)

| Parameter | Value |
|-----------|-------|
| Command | `trivy image $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$VERSION` |
| Artifact | `trivy-report.json` |
| Depends on | BUILD-DOCKER |

#### 5b. Helm Package

| Parameter | Value |
|-----------|-------|
| Chart path | `infra/kubernetes/lenie/helm/lenie-ai-server` |
| Version update | Set `version` in `Chart.yaml` to `$HELM_VERSION` |
| Command | `helm package infra/kubernetes/lenie/helm/lenie-ai-server` |
| Artifact | `lenie-ai-server-$HELM_VERSION.tgz` |
| Depends on | BUILD-DOCKER (for version) |

### Stage 6: DEPLOY

#### 6a. Push Docker Image

| Parameter | Value |
|-----------|-------|
| Registry | Docker Hub |
| Requires | `DOCKER_HUB_USERNAME`, `DOCKER_HUB_TOKEN` |
| Depends on | BUILD-DOCKER |

**Commands:**
```bash
docker login -u "$DOCKER_HUB_USERNAME" -p "$DOCKER_HUB_TOKEN"
docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$VERSION
docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:latest
```

#### 6b. Publish Helm Chart

| Parameter | Value |
|-----------|-------|
| Target | S3 bucket `lenie-helm` |
| Depends on | BUILD-HELM |

**Commands:**
```bash
mkdir helm-repository
cp lenie-ai-server-*.tgz helm-repository/
aws s3 sync s3://lenie-helm/ helm-repository
helm repo index helm-repository/
aws s3 sync helm-repository s3://lenie-helm/
```

### Stage 7: CLEANUP

**Purpose:** Remove old Docker images from the runner to free disk space.

**Command:**
```bash
infra/docker/docker_images_clean.sh --remove-name lenie
```

### Stage 8: INFRA-STOP

**Purpose:** Stop the EC2 runner instance to save costs. Mirrors INFRA-START.

**Command:**
```bash
aws ec2 stop-instances --instance-ids $INSTANCE_ID
```

**Important:** This stage should run **always** (even if previous stages failed) to avoid leaving the instance running.

---

## Pipeline Triggers

| Trigger | Stages executed |
|---------|-----------------|
| Push to `dev` | All stages (VALIDATE exports fallback version) |
| Push to `main` | All stages |
| MR/PR targeting `main` | All stages (VALIDATE enforces semver label) |

---

## Platform-specific Patterns

Detailed configurations for each CI/CD platform:

| Platform | Status | Documentation |
|----------|--------|---------------|
| **GitLab CI** | Archived | [GitLabCI.md](GitLabCI.md) (backend + frontend pipelines) |
| **CircleCI** | Archived (minimal) | [CircleCI.md](CircleCI.md) |
| **Jenkins** | Archived | [Jenkins.md](Jenkins.md) |

When creating a new pipeline, use the [Target Pipeline Specification](#target-pipeline-specification) above and translate it to the platform's syntax.

---

## AWS Infrastructure

EC2 instance lifecycle management (start/stop for CI/CD runners), AWS CLI configuration, and scripts for manually starting instances with automatic Route 53 DNS updates.

> **Full details:** [AWS_Infrastructure.md](AWS_Infrastructure.md)

## Preparing Self-hosted EC2 Runner

Instructions for preparing an EC2 instance (Amazon Linux 2023) as a self-hosted CI/CD runner — including Python 3.11, Go, Docker, security tools (Semgrep, OSV Scanner), and uv.

> **Full instructions:** [AWS_EC2_Runner_Setup.md](AWS_EC2_Runner_Setup.md)

## Self-hosted Jenkins on EC2

Jenkins is currently not in use. Documentation covers: Makefile target restoration, automatic Security Group configuration (IMDSv2), SSL certificates (Let's Encrypt → Java KeyStore), GitHub webhooks.

> **Full instructions:** [Jenkins.md](Jenkins.md)

## Tools Reference

Installation, configuration, and invocation instructions for all tools used in the pipeline.

> **Detailed setup commands:** [CI_CD_Tools.md](CI_CD_Tools.md)

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `us-east-1` |
| `INSTANCE_ID` | EC2 runner instance ID | `i-03908d34c63fce042` |
| `CI_REGISTRY_IMAGE` | Docker image name | `lenie-ai-server` |
| `TAG_VERSION` | Fallback Docker tag version | `0.2.11.6` |

### Secrets (stored in CI/CD platform)

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS access key (GitLab variant: `GITLAB_AWS_ACCESS_KEY_ID`) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (GitLab variant: `GITLAB_AWS_SECRET_ACCESS_KEY`) |
| `DOCKER_HUB_USERNAME` | Docker Hub username |
| `DOCKER_HUB_TOKEN` | Docker Hub access token |
| `QODANA_TOKEN` | Qodana token (optional) |

## Artifacts

### List of Artifacts Generated by the Pipeline

| Artifact | Stage | Description |
|----------|-------|-------------|
| `semgrep-report.json` | SECURITY-CODE | Semgrep static analysis report |
| `trufflehog.txt` | SECURITY-CODE | Detected secrets report |
| `osv_scan_results.json` | SECURITY-CODE | Dependency vulnerability report |
| `trivy-report.json` | SECURITY-DOCKER | Docker image vulnerability report |
| `pytest-results/` | TEST | Pytest test reports (HTML) |
| `flake_reports/` | TEST | Flake8 code style reports (HTML) |
| `lenie-ai-server-*.tgz` | BUILD-HELM | Helm chart package |

---

## Working with GitHub Without CI/CD

When working with GitHub as the repository host **without an active CI/CD pipeline**, it is recommended to install the [GitHub CLI (`gh`)](https://cli.github.com/) tool. It provides convenient access to GitHub features directly from the terminal — pull requests, issues, Dependabot alerts, and more.

### Installation

| Platform | Command |
|----------|---------|
| **Windows** | `winget install --id GitHub.cli` |
| **macOS** | `brew install gh` |
| **Linux (Debian/Ubuntu)** | See [official instructions](https://github.com/cli/cli/blob/trunk/docs/install_linux.md) |

After installation, authenticate with:
```bash
gh auth login
```

### Claude Code Integration

When using Claude Code with `gh`, add the necessary commands to the allowed permissions list in `.claude/settings.local.json`. For example, to allow querying Dependabot alerts:

```json
{
  "permissions": {
    "allow": [
      "Bash(gh api repos/<owner>/<repo>/dependabot/alerts:*)"
    ]
  }
}
```

### Useful Commands

```bash
# Dependabot security alerts
gh api repos/<owner>/<repo>/dependabot/alerts

# Pull requests
gh pr list
gh pr create --title "..." --body "..."
gh pr view <number>

# Issues
gh issue list
gh issue create --title "..." --body "..."
```

---

## How to Use This Documentation

When creating a new CI/CD pipeline:

1. **Choose a platform** (GitHub Actions, GitLab CI, CircleCI, Jenkins, etc.)
2. **Follow the [Target Pipeline Specification](#target-pipeline-specification)** — implement each stage in the platform's syntax
3. **Configure infrastructure** — if using a self-hosted runner, see [AWS Infrastructure](#aws-infrastructure)
4. **Install tools on runner** — see [AWS_EC2_Runner_Setup.md](AWS_EC2_Runner_Setup.md)
5. **Set variables and secrets** — list in [Environment Variables](#environment-variables)
6. **Review platform examples** — check [Platform-specific Patterns](#platform-specific-patterns) for reference

---

*Reference documentation generated from historical configurations: GitLab CI, CircleCI, Jenkins*
