#! /bin/bash

set -xe

## The Karpenter installation follow: https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/


# The core-dns addons will report issue on web interface if number of nodes is smaller than 2

export CLUSTER_NAME="jenkins-karpenter-poc2"
export K8S_VERSION="1.30"
export KARPENTER_VERSION="0.37.0"
export AWS_DEFAULT_REGION="eu-west-1"
export INSTANCE_TYPE="t2.medium"
export AWS_PROFILE="odkrywca-dev1-Administrator"
export STEP=4

export KARPENTER_NAMESPACE="kube-system"

export AWS_PARTITION="aws" # if you are not using standard partitions, you may need to configure to aws-cn / aws-us-gov
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export TEMPOUT="$(mktemp)"
export ARM_AMI_ID="$(aws ssm get-parameter --name /aws/service/eks/optimized-ami/${K8S_VERSION}/amazon-linux-2-arm64/recommended/image_id --query Parameter.Value --output text)"
export AMD_AMI_ID="$(aws ssm get-parameter --name /aws/service/eks/optimized-ami/${K8S_VERSION}/amazon-linux-2/recommended/image_id --query Parameter.Value --output text)"
export GPU_AMI_ID="$(aws ssm get-parameter --name /aws/service/eks/optimized-ami/${K8S_VERSION}/amazon-linux-2-gpu/recommended/image_id --query Parameter.Value --output text)"


if [[ $STEP -le 2 ]]; then
echo "STEP 1: Setup Karpenter permissions etc"
curl -fsSL https://raw.githubusercontent.com/aws/karpenter-provider-aws/v"${KARPENTER_VERSION}"/website/content/en/preview/getting-started/getting-started-with-karpenter/cloudformation.yaml  > "${TEMPOUT}" \
&& aws cloudformation deploy \
  --stack-name "Karpenter-${CLUSTER_NAME}" \
  --template-file "${TEMPOUT}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "ClusterName=${CLUSTER_NAME}"
fi

if [[ $STEP -le 2 ]]; then
  echo ">STEP 2: Creating EKS cluster usting eksctl command"
eksctl create cluster -f - <<EOF
---
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: ${CLUSTER_NAME}
  region: ${AWS_DEFAULT_REGION}
  version: "${K8S_VERSION}"

iam:
  withOIDC: true
  serviceAccounts:
  - metadata:
      name: aws-load-balancer-controller
      namespace: kube-system
    wellKnownPolicies:
      awsLoadBalancerController: true

managedNodeGroups:
- name: ${CLUSTER_NAME}-workers1
  instanceType: ${INSTANCE_TYPE}
  amiFamily: AmazonLinux2
  desiredCapacity: 2
  minSize: 1
  maxSize: 10
  privateNetworking: true
  spot: true
  iam:
    withAddonPolicies:
      autoScaler: true

addons:
  - name: aws-ebs-csi-driver
    wellKnownPolicies:
      ebsCSIController: true

EOF
fi

echo "You can now add your now cluster into your kubeconfig using command:"
echo ""
echo "aws eks update-kubeconfig --region ${AWS_DEFAULT_REGION} --name ${CLUSTER_NAME} --profile ${AWS_PROFILE}"
echo ""


echo "TO delete cluster, use command:"
echo ""
echo "eksctl delete cluster  --region ${AWS_DEFAULT_REGION} --name ${CLUSTER_NAME} --profile ${AWS_PROFILE}"
echo ""

exit 0