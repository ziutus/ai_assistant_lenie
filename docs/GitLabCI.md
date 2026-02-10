# GitLab CI Pattern

Example GitLab CI configuration with a self-hosted runner on EC2.

> **Parent document:** [CI_CD.md](CI_CD.md) — general CI/CD pipeline rules and conventions.

> **Source file:** `infra/old_gitlab_config.yaml` (archived — GitLab CI is no longer active)

## Architecture

```
.pre (start_runner — start EC2)
    ↓
validate-main (version tag validation on MR to main)
    ↓
test + security-checks (parallel)
    ↓
build (Docker image)
    ↓
build-helm (Helm chart package)
    ↓
security-checks-docker (Trivy scan)
    ↓
deploy (push Docker + publish Helm to S3)
    ↓
clean-node (remove old Docker images)
    ↓
.post (stop_runner — stop EC2)
```

## Variables

```yaml
variables:
  CI: "false"
  AWS_REGION: "us-east-1"
  INSTANCE_ID: "i-03908d34c63fce042"
  CI_REGISTRY_IMAGE: "lenie-ai-server"
  TAG_VERSION: "0.2.11.6"
```

## Workflow Trigger

Pipeline runs **only on merge request events**:

```yaml
workflow:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

Build/deploy jobs additionally filter by branch (`dev`, `main`) or MR target `main`.

## Jobs

### 1. start_runner (stage: .pre)

Starts the EC2 runner instance before the pipeline begins.

```yaml
start_runner:
  stage: .pre
  variables:
    GIT_STRATEGY: none
  before_script:
    - apt-get update -y && apt-get install -y awscli
    - aws configure set aws_access_key_id $GITLAB_AWS_ACCESS_KEY_ID
    - aws configure set aws_secret_access_key $GITLAB_AWS_SECRET_ACCESS_KEY
    - aws configure set region $AWS_REGION
  script:
    - aws ec2 start-instances --instance-ids $INSTANCE_ID
```

### 2. validate_merge_request (stage: validate-main)

Validates that MRs targeting `main` have a semver label (`x.y.z`) and that the version is higher than the latest git tag.

**Logic:**
- Requires at least one MR label matching `^[0-9]+\.[0-9]+\.[0-9]+$`
- Compares against existing git tags using numeric comparison
- Exports `NEW_VERSION` via `build.env` artifact for downstream jobs

### 3. job-pytest (stage: test)

```yaml
job-pytest:
  tags: [AWS]
  before_script:
    - pip install -r requirements.txt
  script:
    pytest --self-contained-html --html=pytest-results/ || true
  artifacts:
    when: always
    paths:
      - pytest-results/
```

### 4. job-helm-lint (stage: test)

```yaml
job-helm-lint:
  tags: [AWS]
  script:
    - helm lint infra/kubernetes/lenie/helm/lenie-ai-server
```

### 5. job-style-tool-flake8-scan (stage: test)

```yaml
job-style-tool-flake8-scan:
  tags: [AWS]
  before_script:
    - pip3 install flake8-html
  script:
    - flake8 --format=html --htmldir=flake_reports/
  artifacts:
    when: always
    paths:
      - flake_reports/
```

### 6. Security checks (stage: security-checks) — parallel

| Job | Tool | Command | Artifact |
|-----|------|---------|----------|
| `job-security-tool-semgrep` | Semgrep | `semgrep --config=auto --output semgrep-report.json` | `semgrep-report.json` |
| `job-security-tool-trufflehog` | TruffleHog | `docker run trufflesecurity/trufflehog:latest git file://. --only-verified --bare` | `trufflehog.txt` |
| `job-security-tool-osv_scan` | OSV Scanner | `/usr/local/bin/osv-scanner scan --lockfile requirements.txt` | `osv_scan_results.json` |

Hidden job (not auto-triggered):

| Job | Tool | Image | Artifact |
|-----|------|-------|----------|
| `.qodana` | Qodana | `jetbrains/qodana-python-community:2024.1` | `.qodana/cache` |

### 7. job-build-docker-image (stage: build)

Builds Docker image using version from `validate_merge_request` (or fallback `TAG_VERSION`).

```yaml
job-build-docker-image:
  tags: [AWS]
  needs: [validate_merge_request]
  script:
    - docker build -t $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$VERSION .
    - docker tag ... :latest
  artifacts:
    reports:
      dotenv: build.env    # Exports VERSION, HELM_VERSION
```

### 8. job-security-tool-trivy (stage: security-checks-docker)

Scans the built Docker image for vulnerabilities.

```yaml
job-security-tool-trivy:
  tags: [AWS]
  needs: [job-build-docker-image]
  script:
    - /usr/local/bin/trivy image $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$VERSION > trivy-report.json || true
  artifacts:
    paths:
      - trivy-report.json
```

### 9. job-build-helm (stage: build-helm)

Packages the Helm chart with the correct version.

```yaml
job-build-helm:
  tags: [AWS]
  needs: [job-build-docker-image]
  script:
    - sed -i "s/version: .*/version: ${HELM_VERSION}/" infra/kubernetes/lenie/helm/lenie-ai-server/Chart.yaml
    - helm package infra/kubernetes/lenie/helm/lenie-ai-server
  artifacts:
    paths:
      - lenie-ai-server-${HELM_VERSION}.tgz
```

### 10. Deploy jobs (stage: deploy) — parallel

**job-push-docker-image:**
```yaml
job-push-docker-image:
  tags: [AWS]
  needs: [job-build-docker-image]
  before_script:
    - docker login -u "$DOCKER_HUB_USERNAME" -p "$DOCKER_HUB_TOKEN"
  script:
    - docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$VERSION
    - docker push $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:latest
```

**job-publish-helm:**
```yaml
job-publish-helm:
  tags: [AWS]
  needs: [job-build-helm]
  script:
    - mkdir helm-repository
    - cp lenie-ai-server-*.tgz helm-repository/
    - aws s3 sync s3://lenie-helm/ helm-repository
    - helm repo index helm-repository/
    - aws s3 sync helm-repository s3://lenie-helm/
```

### 11. job-clean-docker-image (stage: clean-node)

```yaml
job-clean-docker-image:
  tags: [AWS]
  script:
    - infra/docker/docker_images_clean.sh --remove-name lenie
```

### 12. stop_runner (stage: .post)

Stops the EC2 runner instance after the pipeline completes (mirrors `start_runner`).

## Parallel Execution

Jobs within the same stage run in parallel:
- **test:** `job-pytest`, `job-helm-lint`, `job-style-tool-flake8-scan`
- **security-checks:** `job-security-tool-semgrep`, `job-security-tool-trufflehog`, `job-security-tool-osv_scan`

## Self-hosted Runner

All jobs tagged `AWS` run on a self-hosted GitLab runner installed on the EC2 instance.
- **Instance ID:** `i-03908d34c63fce042`
- **Runner setup:** see [AWS_EC2_Runner_Setup.md](AWS_EC2_Runner_Setup.md)

## Secrets (CI/CD Variables)

| Variable | Description |
|----------|-------------|
| `GITLAB_AWS_ACCESS_KEY_ID` | AWS access key for EC2 start/stop |
| `GITLAB_AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `DOCKER_HUB_USERNAME` | Docker Hub username |
| `DOCKER_HUB_TOKEN` | Docker Hub access token |
| `QODANA_TOKEN` | Qodana Cloud token (optional) |
