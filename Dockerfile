# Use an official Python runtime as a parent image
FROM python:3.11-slim AS build-stage

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY requirements.txt /app/requirements.txt

RUN apt-get update && apt-get install -y curl

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY library /app/library/
#COPY tests /app/tests/
COPY server.py /app/

FROM python:3.11-slim
WORKDIR /app
COPY --from=build-stage /app/* .

# Define the command to run your application
CMD ["python", "server.py"]

# Expose port 5000 for the Flask application
EXPOSE 5000
