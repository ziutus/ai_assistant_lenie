# Frontend Deployment

Manual deployment guide for Lenie AI frontend applications to AWS (S3 + CloudFront).

> **2026-07-02:** The `app.dev.lenie-ai.eu` and `app2.dev.lenie-ai.eu` hosting stacks were **deleted** — those frontends required the AWS document API (`app-server-db`), which was decommissioned; they now run only against the Docker/NAS backend. Their `deploy.sh` scripts will fail (SSM parameters gone) until the stacks are restored. Restoration: [aws-serverless-restoration.md](aws-serverless-restoration.md). The sections below describing app/app2 are kept as reference for that restoration.

## Overview

Currently hosted via S3 + CloudFront:

| App | URL | Deploy Script | S3 Bucket | Status |
|-----|-----|---------------|-----------|--------|
| Landing page | `www.lenie-ai.eu` | *(no script yet)* | `lenie-prod-landing-web` | active |
| React app | `app.dev.lenie-ai.eu` | `web_interface_react/deploy.sh` | `lenie-dev-app-web` | **hosting deleted 2026-07-02** |
| Admin panel | `app2.dev.lenie-ai.eu` | `web_interface_app2/deploy.sh` | `lenie-dev-app2-web` | **hosting deleted 2026-07-02** |

## Prerequisites

- AWS CLI configured with appropriate credentials
- Node.js and npm installed
- SSM Parameter Store populated by CloudFormation stacks (`s3-app-web`, `s3-app2-web`, `cloudfront-app`, `cloudfront-app2`)

## Deploy Scripts

Both `web_interface_react` and `web_interface_app2` have identical deploy script interfaces. The scripts resolve infrastructure configuration (S3 bucket name, CloudFront distribution ID) from AWS SSM Parameter Store — no hardcoded values.

### Usage

```bash
cd web_interface_react   # or web_interface_app2
./deploy.sh                      # Full: npm install + build + S3 sync + CF invalidation
./deploy.sh --skip-build         # Skip npm install and build (use existing build/)
./deploy.sh --skip-invalidation  # Skip CloudFront cache invalidation
./deploy.sh --help               # Show usage
```

### What the Script Does

1. **Resolves config from SSM** — reads S3 bucket name and CloudFront distribution ID
2. **Installs dependencies** — `npm install` (skippable with `--skip-build`)
3. **Builds production bundle** — `npm run build` (output: `build/`)
4. **Syncs to S3** — `aws s3 sync build/ s3://<bucket> --delete`
5. **Invalidates CloudFront cache** — `aws cloudfront create-invalidation --paths "/*"` (skippable)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_CODE` | `lenie` | Project code used in SSM parameter paths |
| `ENVIRONMENT` | `dev` | Environment name (`dev`, future: `prod`, `qa`) |
| `AWS_REGION` | `us-east-1` | AWS region |

### SSM Parameters

The deploy scripts read the following SSM parameters (exported by CloudFormation):

**React app (`web_interface_react`):**
- `/${PROJECT_CODE}/${ENVIRONMENT}/s3/app-web/name` — S3 bucket name
- `/${PROJECT_CODE}/${ENVIRONMENT}/cloudfront/app/id` — CloudFront distribution ID

**Admin panel (`web_interface_app2`):**
- `/${PROJECT_CODE}/${ENVIRONMENT}/s3/app2-web/name` — S3 bucket name
- `/${PROJECT_CODE}/${ENVIRONMENT}/cloudfront/app2/id` — CloudFront distribution ID

These parameters are created by CloudFormation templates:
- `s3-app-web.yaml` / `s3-app2-web.yaml` — bucket name, ARN, domain name
- `cloudfront-app.yaml` / `cloudfront-app2.yaml` — distribution ID, domain name

### Git Bash Compatibility

The scripts include `MSYS_NO_PATHCONV=1` for AWS CLI calls that use SSM paths starting with `/`. This prevents Git Bash (MSYS) from incorrectly converting these paths to Windows paths. The scripts work in both Git Bash and WSL.

## CloudFront Cache Invalidation

After deploying, CloudFront cache invalidation takes 1-5 minutes to propagate globally. Use `--skip-invalidation` if deploying multiple times in quick succession (invalidate only on the final deploy).

To check invalidation status:

```bash
aws cloudfront get-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --id <INVALIDATION_ID>
```

## Historical Context

The React frontend was originally deployed via a GitLab CI pipeline (archived at `infra/archive/gitlab-ci-frontend.yml`), then migrated to AWS Amplify (now removed), and finally back to S3 + CloudFront with manual deploy scripts.
