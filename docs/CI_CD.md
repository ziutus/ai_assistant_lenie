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
3. [CircleCI Pattern](#circleci-pattern) → [CircleCI.md](CircleCI.md)
4. [AWS Infrastructure](#aws-infrastructure) → [AWS_Infrastructure.md](AWS_Infrastructure.md)
5. [Preparing Self-hosted EC2 Runner](#preparing-self-hosted-ec2-runner) → [AWS_EC2_Runner_Setup.md](AWS_EC2_Runner_Setup.md)
6. [Self-hosted Jenkins on EC2](#self-hosted-jenkins-on-ec2) → [Jenkins.md](Jenkins.md)
7. [Pipeline Stages](#pipeline-stages) — tools detail in [CI_CD_Tools.md](CI_CD_Tools.md)
8. [Security Tools](#security-tools)
9. [Tests and Code Quality](#tests-and-code-quality)
10. [Docker — Local Development and Deployment](#docker--local-development-and-deployment) → [Docker_Local.md](Docker_Local.md)
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

Self-hosted runner on EC2 with workflow: start-ec2 → run tests → build Docker → stop-ec2. Uses `itsnap/itsnap-runner` resource class, `uv` for dependency management, JUnit XML test results.

> **Full configuration:** [CircleCI.md](CircleCI.md)

## AWS Infrastructure

EC2 instance lifecycle management (start/stop for CI/CD runners), AWS CLI configuration, and scripts for manually starting instances with automatic Route 53 DNS updates.

> **Full details:** [AWS_Infrastructure.md](AWS_Infrastructure.md)

## Preparing Self-hosted EC2 Runner

Instructions for preparing an EC2 instance (Amazon Linux 2023) as a self-hosted CI/CD runner — including Python 3.11, Go, Docker, security tools (Semgrep, OSV Scanner), and uv.

> **Full instructions:** [AWS_EC2_Runner_Setup.md](AWS_EC2_Runner_Setup.md)

## Self-hosted Jenkins on EC2

Jenkins is currently not in use. Documentation covers: Makefile target restoration, automatic Security Group configuration (IMDSv2), SSL certificates (Let's Encrypt → Java KeyStore), GitHub webhooks.

> **Full instructions:** [Jenkins.md](Jenkins.md)

## Pipeline Stages

1. Environment preparation (uv, dependencies)
2. Creating report directories
3. Security checks + tests (parallel)
4. Docker build and deploy

> **Detailed setup commands:** [CI_CD_Tools.md](CI_CD_Tools.md)

## Security Tools

| Tool | Purpose | Artifact |
|------|---------|----------|
| Semgrep | Static code analysis (vulnerability detection) | `semgrep-report.json` |
| TruffleHog | Secret detection in repository history | `trufflehog.txt` |
| OSV Scanner | Dependency vulnerability scanning | `osv_scan_results.json` |
| Qodana | JetBrains static analysis (PyCharm inspections, SARIF format) | `qodana.sarif.json` |
| pip-audit | PyPI advisory database check | — |
| Bandit | Python security linter | — |
| Safety | Dependency vulnerability check | — |

Local development: all tools available via `make security-all` (uses `uvx`, no install needed).

> **Installation, configuration, invocation:** [CI_CD_Tools.md](CI_CD_Tools.md)

## Tests and Code Quality

| Tool | Purpose | Artifact |
|------|---------|----------|
| Pytest | Unit and integration tests (HTML report) | `pytest-results/` |
| Flake8 | Code style checking (HTML report) | `flake_reports/` |

> **Commands and flags:** [CI_CD_Tools.md](CI_CD_Tools.md)

## Docker — Local Development and Deployment

Docker Compose for local dev (build/dev/down), Docker Hub image build/push workflow, image cleanup.

> **Full details:** [Docker_Local.md](Docker_Local.md)

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

**Jenkins / CircleCI:** See [Jenkins.md](Jenkins.md) and [CircleCI.md](CircleCI.md) for platform-specific parallel execution patterns.

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
