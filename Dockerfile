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

# Create a non-root user and change ownership of the app directory
RUN useradd -m lenie-ai-server && chown -R lenie-ai-server:lenie-ai-server /app

# Switch to the lenie-ai-server user
USER lenie-ai-server

# Expose port 5000 for the Flask application
EXPOSE 5000

# Define the command to run your application
CMD ["python", "server.py"]
