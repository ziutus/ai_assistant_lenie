#!/bin/bash

# Get a list of all Docker images
images=$(docker images -q)

# Check if the images list is not empty
if [ -z "$images" ]; then
  echo "No images to remove."
else
  echo "Removing all Docker images..."
  docker image rm -f $images
fi

# Prune system - this will remove:
# - all stopped containers
# - all networks not used by at least one container
# - all dangling images
# - all build cache
echo "Pruning Docker system..."
docker system prune -a -f

# Optionally, if you want to also remove all unused volumes, include the --volumes flag
# docker system prune -a -f --volumes

exit 0
