#! /bin/bash

set -e

STEP=10
export CLUSTER_NAME="jenkins-karpenter-poc2"
export K8S_VERSION="1.30"
export KARPENTER_VERSION="0.37.0"
export AWS_DEFAULT_REGION="eu-west-1"
export INSTANCE_TYPE="t2.medium"
export AWS_PROFILE="odkrywca-dev1-Administrator"
export AWS_PARTITION="aws" # if you are not using standard partitions, you may need to configure to aws-cn / aws-us-gov


function usage() {

cat << EOF
usage: $0 options

--create - create cluster
--delete - delete cluster
--step STEP - run creation of cluster from step STEP, useful during debugging of script
-h|--help - show this help message

EOF
}

while [ $# -gt 0 ];
do
  case $1 in
    -h|--help) shift; usage;;
    --create) shift; ACTION="create";;
    --delete) shift; ACTION="delete";;
    -s|--step) shift; STEP=$1; echo "Step $STEP"; shift;;
    *) echo "Wrong option $1"; exit 1;
  esac
done;

echo "ACTION: ${ACTION}"

if [ "$ACTION" != "create" ] && [ "$ACTION" != "delete" ]; then
  echo "Error: ACTION must be 'create' or 'delete'."
  usage
  exit 1
fi

## The Karpenter installation follow: https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/


# The core-dns addons will report issue on web interface if number of nodes is smaller than 2


export KARPENTER_NAMESPACE="kube-system"
TEMPOUT="$(mktemp)"
export TEMPOUT

if [[ ${ACTION} == "create" ]] && [[ $STEP -le 1 ]]; then
echo "STEP 1: Setup Karpenter permissions etc"
curl -fsSL https://raw.githubusercontent.com/aws/karpenter-provider-aws/v"${KARPENTER_VERSION}"/website/content/en/preview/getting-started/getting-started-with-karpenter/cloudformation.yaml  > "${TEMPOUT}" \
&& aws cloudformation deploy \
  --stack-name "Karpenter-${CLUSTER_NAME}" \
  --template-file "${TEMPOUT}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides "ClusterName=${CLUSTER_NAME}"
fi

if [[ ${ACTION} == "create" ]] && [[ $STEP -le 2 ]]; then
  echo ">STEP 2: Creating EKS cluster usting eksctl command"
  export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

eksctl create cluster -f - <<EOF
---
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: ${CLUSTER_NAME}
  region: ${AWS_DEFAULT_REGION}
  version: "${K8S_VERSION}"
  tags:
    karpenter.sh/discovery: ${CLUSTER_NAME}

iam:
  withOIDC: true
  podIdentityAssociations:
  - namespace: "${KARPENTER_NAMESPACE}"
    serviceAccountName: karpenter
    roleName: ${CLUSTER_NAME}-karpenter
    permissionPolicyARNs:
    - arn:${AWS_PARTITION}:iam::${AWS_ACCOUNT_ID}:policy/KarpenterControllerPolicy-${CLUSTER_NAME}
  serviceAccounts:
  - metadata:
      name: aws-load-balancer-controller
      namespace: kube-system
    wellKnownPolicies:
      awsLoadBalancerController: true
iamIdentityMappings:
- arn: "arn:${AWS_PARTITION}:iam::${AWS_ACCOUNT_ID}:role/KarpenterNodeRole-${CLUSTER_NAME}"
  username: system:node:{{EC2PrivateDNSName}}
  groups:
  - system:bootstrappers
  - system:nodes
  ## If you intend to run Windows workloads, the kube-proxy group should be specified.
  # For more information, see https://github.com/aws/karpenter/issues/5099.
  # - eks:kube-proxy-windows



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
  - name: eks-pod-identity-agent
  - name: aws-ebs-csi-driver
    wellKnownPolicies:
      ebsCSIController: true

EOF

  export CLUSTER_ENDPOINT="$(aws eks describe-cluster --name "${CLUSTER_NAME}" --query "cluster.endpoint" --output text)"
  export KARPENTER_IAM_ROLE_ARN="arn:${AWS_PARTITION}:iam::${AWS_ACCOUNT_ID}:role/${CLUSTER_NAME}-karpenter"

  echo "${CLUSTER_ENDPOINT} ${KARPENTER_IAM_ROLE_ARN}"
fi

if [[ ${ACTION} == "create" ]] && [[ $STEP -le 3 ]]; then
  echo "Linking service role for SPOT EC2 roles"
  aws iam create-service-linked-role --aws-service-name spot.amazonaws.com || true
# If the role has already been successfully created, you will see:
# An error occurred (InvalidInput) when calling the CreateServiceLinkedRole operation: Service role name AWSServiceRoleForEC2Spot has been taken in this account, please try a different suffix.

fi

if [[ ${ACTION} == "create" ]] && [[ $STEP -le 4 ]]; then
    echo "STEP 4: installing karpenter using helm"
    helm upgrade --install karpenter oci://public.ecr.aws/karpenter/karpenter --version "${KARPENTER_VERSION}" --namespace "${KARPENTER_NAMESPACE}" --create-namespace \
  --set "settings.clusterName=${CLUSTER_NAME}" \
  --set "settings.interruptionQueue=${CLUSTER_NAME}" \
  --set controller.resources.requests.cpu=1 \
  --set controller.resources.requests.memory=1Gi \
  --set controller.resources.limits.cpu=1 \
  --set controller.resources.limits.memory=1Gi \
  --wait

fi

if [[ ${ACTION} == "create" ]] && [[ $STEP -le 5 ]]; then
  export ARM_AMI_ID="$(aws ssm get-parameter --name /aws/service/eks/optimized-ami/${K8S_VERSION}/amazon-linux-2-arm64/recommended/image_id --query Parameter.Value --output text)"
  export AMD_AMI_ID="$(aws ssm get-parameter --name /aws/service/eks/optimized-ami/${K8S_VERSION}/amazon-linux-2/recommended/image_id --query Parameter.Value --output text)"
  export GPU_AMI_ID="$(aws ssm get-parameter --name /aws/service/eks/optimized-ami/${K8S_VERSION}/amazon-linux-2-gpu/recommended/image_id --query Parameter.Value --output text)"

  cat <<EOF | envsubst | kubectl apply -f -
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      requirements:
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: kubernetes.io/os
          operator: In
          values: ["linux"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot"]
        - key: karpenter.k8s.aws/instance-category
          operator: In
          values: ["c", "m", "r"]
        - key: karpenter.k8s.aws/instance-generation
          operator: Gt
          values: ["2"]
      nodeClassRef:
        apiVersion: karpenter.k8s.aws/v1beta1
        kind: EC2NodeClass
        name: default
  limits:
    cpu: 1000
  disruption:
    consolidationPolicy: WhenUnderutilized
    expireAfter: 720h # 30 * 24h = 720h
---
apiVersion: karpenter.k8s.aws/v1beta1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiFamily: AL2 # Amazon Linux 2
  role: "KarpenterNodeRole-${CLUSTER_NAME}" # replace with your cluster name
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: "${CLUSTER_NAME}" # replace with your cluster name
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: "${CLUSTER_NAME}" # replace with your cluster name
  amiSelectorTerms:
    - id: "${ARM_AMI_ID}"
    - id: "${AMD_AMI_ID}"
#   - id: "${GPU_AMI_ID}" # <- GPU Optimized AMD AMI
    - name: "amazon-eks-node-${K8S_VERSION}-*" # <- automatically upgrade when a new AL2 EKS Optimized AMI is released. This is unsafe for production workloads. Validate AMIs in lower environments before deploying them to production.
EOF
fi

if [[ ${ACTION} == "create" ]] && [[ $STEP -le 6 ]]; then
  echo "STEP 6: installing Ingress controller to manage ALB on AWS"
  helm repo add eks https://aws.github.io/eks-charts
  helm repo update eks

  AWS_VPC_ID=$(aws eks describe-cluster --name ${CLUSTER_NAME} --region ${AWS_DEFAULT_REGION} --query "cluster.resourcesVpcConfig.vpcId" --output text)
  helm install aws-load-balancer-controller eks/aws-load-balancer-controller --namespace kube-system --set clusterName=${CLUSTER_NAME} --set serviceAccount.create=false --set region=${AWS_DEFAULT_REGION} --set vpcId=${AWS_VPC_ID} --set serviceAccount.name=aws-load-balancer-controller
fi

echo "You can now add your now cluster into your kubeconfig using command:"
echo ""
echo "aws eks update-kubeconfig --region ${AWS_DEFAULT_REGION} --name ${CLUSTER_NAME} --profile ${AWS_PROFILE}"
echo ""

if [[ ${ACTION} == "delete" ]]; then
  helm uninstall karpenter --namespace "${KARPENTER_NAMESPACE}"
  aws cloudformation delete-stack --stack-name "Karpenter-${CLUSTER_NAME}"
  aws ec2 describe-launch-templates --filters "Name=tag:karpenter.k8s.aws/cluster,Values=${CLUSTER_NAME}" |
      jq -r ".LaunchTemplates[].LaunchTemplateName" |
      xargs -I{} aws ec2 delete-launch-template --launch-template-name {}
  eksctl delete cluster --name "${CLUSTER_NAME}"
fi

exit 0