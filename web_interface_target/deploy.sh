#!/bin/bash
set -euo pipefail

# Deploy script for web_interface_target (app2.lenie-ai.eu)
# Usage: ./deploy.sh [--skip-build] [--skip-invalidation]

S3_BUCKET="${S3_BUCKET_APP2_WEB:-lenie-dev-app2-web}"
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_APP2_DISTRIBUTION_ID:-E1NHFTM571WQ7L}"
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
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      exit 1
      ;;
  esac
done

echo "=== Deploying web_interface_target to app2.lenie-ai.eu ==="
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
  CI=false npm run build
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
echo "=== Deploy complete: https://app2.lenie-ai.eu ==="
