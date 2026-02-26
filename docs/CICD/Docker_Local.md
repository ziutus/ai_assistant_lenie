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

## Prerequisites

Before running the Docker container with the Lenie application, make sure you have:

* Docker installed on your computer. Installation instructions can be found in the official Docker documentation.

To create a Docker image for the Lenie application, you need a Dockerfile in your project directory. Below is an example process of building the image.

1. Open a terminal in the directory where the Dockerfile is located.

2. Run the following command to build the Docker image:

```bash
docker build -t stalker-server2:latest .
```

* The `-t` flag is used to tag (name) the image, in this case stalker.
* The dot `.` at the end indicates that the Dockerfile is in the current directory.

After the build process is complete, you can run the Docker container with the newly created image by using the command described in the section Running the Application.

## Preparing Local Environment

Install the Vault binary from: https://developer.hashicorp.com/vault/install

```bash
docker volume create vault_secrets_dev
docker volume create vault_logs_dev

 docker run -d --name=vault_dev --cap-add=IPC_LOCK -e 'VAULT_LOCAL_CONFIG={"storage": {"file": {"path":
 "/vault/file"}}, "listener": [{"tcp": { "address": "0.0.0.0:8200", "tls_disable": true}}], "default_lease_ttl": "168h", "max_lease_ttl":
"720h", "ui": true}' -v vault_secrets_dev:/vault/file -v vault_logs_dev:/vault/logs -p 8200:8200 hashicorp/vault server
```

```bash
docker pull pgvector/pgvector:pg17
```

```bash
docker run -d --name lenie-ai-db -e POSTGRES_PASSWORD=postgres -p 5432:5432 pgvector/pgvector:pg17
```

```sql
CREATE EXTENSION vector
```

## Running the Application

After starting the application or container, you can access the Lenie application by going to http://localhost:5000 in your web browser.

Running from a local image:
```bash
docker run --rm --env-file .env -p 5000:5000 --name lenie-ai-server -d lenie-ai-server:latest
```

Running from a remote image:

```powershell
docker run --rm --env-file .env -p 5000:5000 --name lenie-ai-server -d lenieai/lenie-ai-server:latest
```

### Docker Compose

```shell
docker-compose.exe create
docker-compose.exe start
```

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DOCKER_HUB_USERNAME` | Docker Hub username | — |
| `DOCKER_HUB_TOKEN` | Docker Hub access token | — |
| `CI_REGISTRY_IMAGE` | Docker image name | `lenie-ai-server` |
| `TAG_VERSION` | Docker tag version | `0.2.11.6` |
