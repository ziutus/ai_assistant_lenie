# EKS Deployment

Amazon EKS (Elastic Kubernetes Service) cluster configuration for Project Lenie.

## Directory Structure

```
eks/
├── README_AWS_EKS.md              # Main lenie-ai cluster documentation
├── iam_polices/
│   └── iam_policy.json            # IAM policy for AWS Load Balancer Controller
└── karpenter/
    ├── README.md                  # Karpenter cluster documentation (Jenkins POC)
    ├── _eks_cluster_with_karpenter.sh  # Automated deployment script with Karpenter
    ├── aws_eksctl.yaml            # eksctl configuration (Jenkins demo cluster)
    └── karpenter_test.yaml        # Karpenter test deployment (inflate)
```

## Clusters

### lenie-ai (main cluster)

Production/development cluster for the Lenie application.

- **Region**: `us-east-1`
- **K8s version**: 1.31
- **Node group**: `workers1`, type `t2.medium`, 2-4 nodes, spot instances
- **Namespace**: `lenie-ai-dev`
- **Network**: Public VPC subnets (shared with RDS - `subnet-066653bc5f645bf3b`, `subnet-065769ce9d50381e3`)
- **OIDC**: enabled (required for IAM service accounts)

#### Creating the cluster

```bash
eksctl create cluster --name lenie-ai --version 1.31 \
  --nodegroup-name workers1 --node-type t2.medium \
  --nodes 2 --nodes-min 2 --nodes-max 4 --spot \
  --vpc-public-subnets subnet-066653bc5f645bf3b,subnet-065769ce9d50381e3 \
  --region us-east-1 \
  --asg-access --external-dns-access --full-ecr-access --alb-ingress-access --with-oidc
```

#### Deleting the cluster

```bash
eksctl delete cluster --name lenie-ai --region us-east-1 --profile lenie_admin
```

After deletion, manually clean up the local kubectl configuration:
```bash
kubectl config delete-cluster <name>
kubectl config delete-user <name>
kubectl config delete-context <name>
```

### lenie-karpenter-poc1 (Karpenter POC)

Test cluster for evaluating Karpenter as an autoscaler.

- **Region**: `us-east-1`
- **K8s version**: 1.30
- **Karpenter**: 0.37.0
- **Node group**: managed + Fargate (for Karpenter)
- **Karpenter instances**: spot, categories c/m/r, generation > 2, amd64 architecture
- **AWS profile**: `lenie_admin`

#### Deployment script

```bash
# Create cluster (all steps)
./karpenter/_eks_cluster_with_karpenter.sh --create

# Create from a specific step (debugging)
./karpenter/_eks_cluster_with_karpenter.sh --create --step 4

# Delete cluster
./karpenter/_eks_cluster_with_karpenter.sh --delete
```

Creation steps:
1. Deploy CloudFormation stack with Karpenter permissions
2. Create EKS cluster via eksctl (managed node group + Fargate)
3. Create service-linked role for spot EC2
4. Install Karpenter via Helm (OCI registry)
5. Configure NodePool and EC2NodeClass (spot, consolidation, 30d expiry)
6. Install AWS Load Balancer Controller (Helm)

## Required Tools

- `eksctl` - EKS cluster creation and management
  - Windows: `choco install -y eksctl`
  - Upgrade: `choco upgrade -y eksctl`
- `kubectl` - Kubernetes management
- `helm` - chart installation (Karpenter, ALB Controller, Reloader)
- `aws` CLI - AWS operations
- `jq` - JSON processing (used in Karpenter script)
- `envsubst` - variable substitution in YAML templates

## Installed Addons and Components

### EBS CSI Driver
EBS volume support as PersistentVolume.

```bash
# IAM service account
eksctl create iamserviceaccount --name ebs-csi-controller-sa \
  --namespace kube-system --cluster lenie-ai \
  --role-name AmazonEKS_EBS_CSI_DriverRole --role-only \
  --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy --approve

# Addon
eksctl create addon --cluster lenie-ai --name aws-ebs-csi-driver --version latest \
  --service-account-role-arn arn:aws:iam::008971653395:role/AmazonEKS_EBS_CSI_DriverRole --force
```

### Metrics Server
CPU/memory metrics for nodes and pods (`kubectl top`).

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### Stakater Reloader
Automatic rolling restart of pods after ConfigMap or Secret changes.

```bash
helm repo add stakater https://stakater.github.io/stakater-charts
helm repo update
helm install stakater/reloader --generate-name
```

Usage: add annotations to your Deployment:
- `configmap.reloader.stakater.com/reload: "foo-configmap"`
- `secret.reloader.stakater.com/reload: "foo-secret"`

### AWS Load Balancer Controller
ALB/NLB management from Kubernetes (Ingress/Service).

IAM policy in `iam_polices/iam_policy.json` - permissions for:
- Creating/deleting load balancers and target groups
- Managing security groups (tagged with `elbv2.k8s.aws/cluster`)
- Registering/deregistering targets
- Integration with ACM, WAF, Shield, Cognito

## Useful Commands

```bash
# Update kubeconfig after cluster creation
aws eks update-kubeconfig --name lenie-ai --region us-east-1

# Rename context
kubectl config rename-context iam-root-account@lenie-ai.us-east-1.eksctl.io lenie_ai_dev

# Set default namespace
kubectl config set-context --current --namespace=lenie-ai-dev

# Enable CloudWatch logging
eksctl utils update-cluster-logging --enable-types=all --region=us-east-1 --cluster=lenie-ai --approve

# Update addons
eksctl get addons --cluster lenie-ai
eksctl update addon --name vpc-cni --cluster lenie-ai --version latest --wait
eksctl update addon --name kube-proxy --cluster lenie-ai --version latest --wait

# Check resource usage
kubectl top nodes
```

## Related Components

- **VPC**: cluster uses subnets defined in `cloudformation/templates/vpc.yaml`
- **Kubernetes manifests**: `infra/kubernetes/kustomize/` - Lenie application K8s configuration (Kustomize with `gke-dev` overlay)
- **Docker image**: `backend/Dockerfile` - backend image deployed to the cluster
