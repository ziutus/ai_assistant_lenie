# syntax=docker/dockerfile:1.7

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1


# Set the working directory in the container
WORKDIR /app

# Update package list and install curl, then clean up apt cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy shared package first (path dependency)
COPY shared_python/unified-config-loader/ /shared_python/unified-config-loader/

# Copy dependency files
COPY backend/pyproject.toml backend/uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --extra docker --no-dev --no-install-project

COPY backend/library ./library/
#COPY backend/tests /app/tests/
COPY backend/server.py .

# Create a non-root user with specific UID and GID, and change ownership of the app directory
RUN groupadd -g 1000 lenie-ai-client && \
    useradd -u 1000 -g lenie-ai-client -m lenie-ai-client && \
    mkdir -p /app/data && \
    chown -R 1000:1000 /app

# Switch to the lenie-ai-client user
USER lenie-ai-client

# Expose port 5000 for the Flask application
EXPOSE 5000

# Define the command to run your application
#CMD ["python", "server.py"]
ENTRYPOINT ["/app/.venv/bin/python", "server.py"]
