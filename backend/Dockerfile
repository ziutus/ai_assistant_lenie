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

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --extra docker --no-dev --no-install-project

COPY library ./library/
#COPY tests /app/tests/
COPY server.py .

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
ENTRYPOINT ["python", "server.py"]
