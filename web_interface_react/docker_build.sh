#! /bin/bash

set -e

DOCKER_IMAGE_NAME="lenie-ai-frontend"
TAG="0.2.7.1"
AWS_REPO=" 008971653395.dkr.ecr.us-east-1.amazonaws.com"
AWS_PROFILE="lenie_admin"
AWS_REGION="us-east-1"
AWS_ECR_NAME_SPACE="lenie-ai-frontend"

echo "Building image locally"
docker build -t ${DOCKER_IMAGE_NAME}:${TAG} .

#echo "Sending image to repo: hub.docker.com"
#docker tag ${DOCKER_IMAGE_NAME}:${TAG} linuxexpertpl/${DOCKER_IMAGE_NAME}:${TAG}
#docker push linuxexpertpl/${DOCKER_IMAGE_NAME}:${TAG}

#echo "Sending image to private repo on AWS"
#docker tag ${DOCKER_IMAGE_NAME}:latest ${AWS_REPO}/${AWS_ECR_NAME_SPACE}/${DOCKER_IMAGE_NAME}:${TAG}

#aws ecr get-login-password --profile ${AWS_PROFILE} --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_REPO}
#docker push ${AWS_REPO}/${AWS_ECR_NAME_SPACE}/${DOCKER_IMAGE_NAME}:${TAG}

exit 0

