#!/bin/bash
set -euo pipefail

# Deploy script for web_interface_react (app.dev.lenie-ai.eu)
# Usage: ./deploy.sh [--skip-build] [--skip-invalidation]
#
# S3 bucket and CloudFront distribution ID are resolved from SSM Parameter Store
# (exported by CloudFormation templates s3-app-web.yaml and cloudfront-app.yaml).

PROJECT_CODE="${PROJECT_CODE:-lenie}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

SKIP_BUILD=false
SKIP_INVALIDATION=false

for arg in "$@"; do
  case $arg in
    --skip-build) SKIP_BUILD=true ;;
    --skip-invalidation) SKIP_INVALIDATION=true ;;
    --help|-h)
      echo "Usage: $0 [--skip-build] [--skip-invalidation]"
      echo ""
      echo "Options:"
      echo "  --skip-build          Skip npm install and build (use existing build/ directory)"
      echo "  --skip-invalidation   Skip CloudFront cache invalidation"
      echo ""
      echo "Environment variables:"
      echo "  PROJECT_CODE          Project code (default: lenie)"
      echo "  ENVIRONMENT           Environment name (default: dev)"
      echo "  AWS_REGION            AWS region (default: us-east-1)"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      exit 1
      ;;
  esac
done

# Resolve S3 bucket and CloudFront distribution ID from SSM
# MSYS_NO_PATHCONV prevents Git Bash from mangling SSM paths starting with /
echo "--- Resolving configuration from SSM ---"
SSM_PREFIX="/${PROJECT_CODE}/${ENVIRONMENT}"
S3_BUCKET=$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --name "${SSM_PREFIX}/s3/app-web/name" --query 'Parameter.Value' --output text --region "$AWS_REGION")
CLOUDFRONT_DISTRIBUTION_ID=$(MSYS_NO_PATHCONV=1 aws ssm get-parameter --name "${SSM_PREFIX}/cloudfront/app/id" --query 'Parameter.Value' --output text --region "$AWS_REGION")

echo "=== Deploying web_interface_react to app.${ENVIRONMENT}.lenie-ai.eu ==="
echo "S3 bucket:      ${S3_BUCKET}"
echo "CloudFront ID:  ${CLOUDFRONT_DISTRIBUTION_ID}"
echo "Region:         ${AWS_REGION}"
echo ""

# Build
if [ "$SKIP_BUILD" = false ]; then
  echo "--- Installing dependencies ---"
  cd "$SCRIPT_DIR"
  npm install

  echo ""
  echo "--- Building production bundle ---"
  npm run build
else
  echo "--- Skipping build (--skip-build) ---"
fi

# Verify build directory exists
if [ ! -d "$BUILD_DIR" ]; then
  echo "ERROR: Build directory not found: ${BUILD_DIR}"
  echo "Run without --skip-build first."
  exit 1
fi

# Deploy to S3
echo ""
echo "--- Syncing to S3 ---"
aws s3 sync "$BUILD_DIR" "s3://${S3_BUCKET}" --delete --region "$AWS_REGION"

# CloudFront invalidation
if [ "$SKIP_INVALIDATION" = false ]; then
  echo ""
  echo "--- Invalidating CloudFront cache ---"
  aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths "/*" \
    --region "$AWS_REGION"
else
  echo "--- Skipping CloudFront invalidation (--skip-invalidation) ---"
fi

echo ""
echo "=== Deploy complete: https://app.${ENVIRONMENT}.lenie-ai.eu ==="
