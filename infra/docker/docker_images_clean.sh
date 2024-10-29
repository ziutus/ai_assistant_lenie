#!/bin/bash

# Initialize variable for remove name
REMOVE_NAME=""

# Parse command line options
while [[ $# -gt 0 ]]; do
  case $1 in
    --remove-name)
      REMOVE_NAME="$2"
      shift
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [ -z "$REMOVE_NAME" ]; then
  echo "No --remove-name option provided. No images will be removed."
else
  # Get a list of all Docker images with names starting with the provided remove name
  images=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^${REMOVE_NAME}")

  # Check if the images list is not empty
  if [ -z "$images" ]; then
    echo "No images to remove with names starting with '${REMOVE_NAME}'."
  else
    echo "Removing Docker images with names starting with '${REMOVE_NAME}'..."
    for image in $images; do
      docker image rm -f $image
    done
  fi
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