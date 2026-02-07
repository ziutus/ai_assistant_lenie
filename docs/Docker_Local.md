# Docker — Local Development and Deployment

Local Docker workflows: development with Docker Compose and image build/push for deployment.

> **Parent document:** [CI_CD.md](CI_CD.md) — general CI/CD pipeline rules and conventions.

## Local Development (Docker Compose)

Docker Compose stack defined in `infra/docker/compose.yaml`:

| Service | Port | Description |
|---------|------|-------------|
| `lenie-ai-server` | 5000 | Flask backend |
| `lenie-ai-db` | 5433 | PostgreSQL with pgvector |
| `lenie-ai-frontend` | 3000 | React frontend |

**Makefile targets:**

```bash
make build   # Build docker containers
make dev     # Run backend and frontend (docker compose up -d)
make down    # Stop and remove containers
```

## Docker Hub — Build, Push, Clean

**Makefile targets:**

```bash
make docker-image    # Build and tag image (version + latest)
make docker-push     # Login and push both tags to Docker Hub
make docker-release  # Build + tag + push (all-in-one)
make docker-clean    # Remove old images matching 'lenie'
```

**What `docker-image` does:**
```bash
docker build -t $DOCKER_HUB_USERNAME/$CI_REGISTRY_IMAGE:$TAG_VERSION .
docker tag  .../$CI_REGISTRY_IMAGE:$TAG_VERSION  .../$CI_REGISTRY_IMAGE:latest
```

**What `docker-push` does:**
```bash
docker login -u "$DOCKER_HUB_USERNAME" -p "$DOCKER_HUB_TOKEN"
docker push  .../$CI_REGISTRY_IMAGE:$TAG_VERSION
docker push  .../$CI_REGISTRY_IMAGE:latest
```

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DOCKER_HUB_USERNAME` | Docker Hub username | — |
| `DOCKER_HUB_TOKEN` | Docker Hub access token | — |
| `CI_REGISTRY_IMAGE` | Docker image name | `lenie-ai-server` |
| `TAG_VERSION` | Docker tag version | `0.2.11.6` |
