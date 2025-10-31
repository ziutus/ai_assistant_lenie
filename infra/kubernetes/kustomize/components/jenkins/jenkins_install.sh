#!/bin/bash

set -xe

# Ustawienie flagi AWS na true (wartość niepusta)
AWS=true

# Zastosowanie zasobów Kubernetes w odpowiedniej kolejności
kubectl apply -f jenkins_1_namespace.yaml
kubectl apply -f jenkins_2_roles.yaml

# Zastosowanie zasobów specyficznych dla AWS
if [ -n "$AWS" ]; then
  kubectl apply -f jenkins_3_storage_aws.yaml
fi

# Zastosowanie deploymentu
kubectl apply -f jenkins_4_deployment.yaml

# Zastosowanie zasobów specyficznych dla AWS po deployment
if [ -n "$AWS" ]; then
  kubectl apply -f jenkins_5_service_aws.yaml
fi

exit 0
