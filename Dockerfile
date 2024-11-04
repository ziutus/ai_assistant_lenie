# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY requirements.txt /app/requirements.txt

# Update package list and install curl, then clean up apt cache
RUN apt-get update && \
    apt-get install -y curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY library /app/library/
#COPY tests /app/tests/
COPY server.py /app/

# Create a non-root user with specific UID and GID, and change ownership of the app directory
RUN groupadd -g 1000 lenie-ai-client && \
    useradd -u 1000 -g lenie-ai-client -m lenie-ai-client && \
    chown -R 1000:1000 /app

# Switch to the lenie-ai-client user
USER 1000

# Expose port 5000 for the Flask application
EXPOSE 5000

# Define the command to run your application
CMD ["python", "server.py"]
