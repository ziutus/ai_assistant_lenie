#!/usr/bin/env bash
set -x

# Ustaw wymagane zmienne środowiskowe
PROJECT_ID="lenie-ai-dev-2025-03"
REGION="europe-west3" # lub inny region
PROJECT_NAME="lenie-ai"
ENVIRONMENT="dev-2025-03"
IMAGE_VERSION="0.0.1"

# Zbuilduj obraz
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${PROJECT_NAME}-${ENVIRONMENT}/convert-ebook:${IMAGE_VERSION}
