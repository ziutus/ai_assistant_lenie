# AWS Amplify Deployment

> **Parent document:** [../README.md](../README.md) — project overview.

## Overview

The Lenie web interfaces can be deployed publicly using [AWS Amplify](https://aws.amazon.com/amplify/), a fully managed hosting service for static and server-rendered web applications. Amplify connects directly to a GitHub repository, automatically builds and deploys on every push.

This is the recommended approach for making the frontend publicly accessible — no servers to manage, built-in HTTPS, custom domains, and CI/CD out of the box.

> **Historical note:** Previously, the frontend was deployed via a GitLab CI pipeline that synced static files to S3 and invalidated CloudFront. See `infra/archive/gitlab-ci-frontend.yml` and [GitLabCI.md](GitLabCI.md) for the archived approach.

## What Can Be Deployed

| Application | Directory | Framework | Amplify Platform |
|-------------|-----------|-----------|-----------------|
| Main frontend (React SPA) | `web_interface_react/` | React 18 (CRA) | WEB (static) |
| Add URL app | `web_add_url_react/` | React (CRA) | WEB (static) |

Both are static React applications that produce a `build/` directory with HTML/JS/CSS files.

## Setting Up Amplify Hosting

### Prerequisites

- AWS account with Amplify access
- GitHub repository (public or private) connected to Amplify
- Custom domain managed in Route53 (optional)

### Step 1: Create Amplify App

```bash
# Via AWS Console: Amplify → New app → Host web app → GitHub
# Or via CLI:
aws amplify create-app \
  --name "lenie-ai-frontend" \
  --repository "https://github.com/<user>/<repo>" \
  --platform WEB \
  --region us-east-1
```

### Step 2: Configure Build Settings

Amplify auto-detects React apps. The build spec should be:

```yaml
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - npm ci
    build:
      commands:
        - npm run build
  artifacts:
    baseDirectory: build
    files:
      - '**/*'
  cache:
    paths:
      - node_modules/**/*
```

### Step 3: Configure SPA Routing

React Router requires a rewrite rule so that all paths serve `index.html`:

In Amplify Console → App settings → Rewrites and redirects, add:

| Source | Target | Type |
|--------|--------|------|
| `/<*>` | `/index.html` | 404 (Rewrite) |

Or the regex variant for file extensions:

| Source | Target | Type |
|--------|--------|------|
| `</^[^.]+$\|\.(?!(css\|gif\|ico\|jpg\|js\|png\|txt\|svg\|woff\|ttf\|map\|json)$)([^.]+$)/>` | `/index.html` | 200 (Rewrite) |

### Step 4: Connect a Branch

```bash
aws amplify create-branch \
  --app-id <APP_ID> \
  --branch-name main \
  --stage PRODUCTION \
  --enable-auto-build
```

### Step 5: Custom Domain (Optional)

```bash
aws amplify create-domain-association \
  --app-id <APP_ID> \
  --domain-name lenie-ai.eu \
  --sub-domain-settings prefix=app,branchName=main
```

Amplify will provide CNAME records to add in Route53. Certificates are managed automatically.

## Environment Variables

The React frontend uses `REACT_APP_*` environment variables set at build time. Configure them in Amplify Console → App settings → Environment variables:

| Variable | Description |
|----------|-------------|
| `REACT_APP_API_URL` | Backend API URL |
| `REACT_APP_API_KEY` | API key (if pre-populated) |

These can also be set per branch for different environments.

## Access Control

### Basic Auth (Password Protection)

Amplify supports built-in Basic Authentication to restrict access:

```bash
# Enable basic auth on the app
aws amplify update-app \
  --app-id <APP_ID> \
  --enable-basic-auth \
  --basic-auth-credentials "$(echo -n 'username:password' | base64)"

# Or per branch
aws amplify update-branch \
  --app-id <APP_ID> \
  --branch-name main \
  --enable-basic-auth \
  --basic-auth-credentials "$(echo -n 'username:password' | base64)"
```

To disable:
```bash
aws amplify update-app --app-id <APP_ID> --no-enable-basic-auth
```

### Checking Current State

```bash
# Check if basic auth is enabled
aws amplify get-app --app-id <APP_ID> \
  --query "app.{name:name,basicAuth:enableBasicAuth,domain:defaultDomain}"

# Check branch settings
aws amplify get-branch --app-id <APP_ID> --branch-name main \
  --query "branch.{name:branchName,stage:stage,basicAuth:enableBasicAuth,lastDeploy:updateTime}"
```

## Useful CLI Commands

```bash
# List all Amplify apps
aws amplify list-apps --query "apps[].{name:name,id:appId,domain:defaultDomain}"

# Check deployment status
aws amplify list-jobs --app-id <APP_ID> --branch-name main --max-items 5

# Trigger a manual build
aws amplify start-job --app-id <APP_ID> --branch-name main --job-type RELEASE

# List custom domains
aws amplify list-domain-associations --app-id <APP_ID>

# View build logs
aws amplify get-job --app-id <APP_ID> --branch-name main --job-id <JOB_ID>
```

## Cost

Amplify Hosting has a generous free tier:
- **Build**: 1000 build minutes/month free
- **Hosting**: 15 GB served/month free, 5 GB stored free

For a low-traffic personal project, Amplify hosting is effectively free.

## Notes

- Amplify creates its own CloudFront distribution behind the scenes — no need to manage CDN separately
- Build happens on Amplify's infrastructure, not locally
- Each branch can have its own subdomain (e.g., `dev.app.lenie-ai.eu`)
- Pull request previews can be enabled for testing before merge
- The backend API (Lambda/Flask) is deployed separately — Amplify only hosts the static frontend
