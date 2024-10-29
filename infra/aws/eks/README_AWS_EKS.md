## ekctrl installation

### Windows

```powershell
choco install -y eksctl
```

```powershell
choco upgrade -y eksctl
```

### cluster creation

```powershell
 eksctl create cluster --name lenie-ai --version 1.31 --nodegroup-name workers1 --node-type t2.medium --nodes 2 --nodes-min 2 --nodes-max 4 --spot --region us-east-1 --asg-access --external-dns-access --full-ecr-access --alb-ingress-access --with-oidc
```

or better to create in VPC where is connected Database (you have to provide information about networks):
```shell
eksctl create cluster --name lenie-ai --version 1.31 --nodegroup-name workers1 --node-type t2.medium --nodes 2 --nodes-min 2 --nodes-max 4 --spot --vpc-public-subnets subnet-066653bc5f645bf3b,subnet-065769ce9d50381e3 --region us-east-1 --asg-access --external-dns-access --full-ecr-access --alb-ingress-access --with-oidc
```
### Associate IAM OIDC provider

Not needed if you created cluster with **--with-oidc**.

```powershell
eksctl utils associate-iam-oidc-provider --region=us-east-1 --cluster=lenie-ai --approve
```

### collect logs in cloudwatch

```powershell
eksctl utils update-cluster-logging --enable-types=all --region=us-east-1 --cluster=lenie-ai
```

### update addons

```powershell
eksctl get addons --cluster lenie-ai
```

```powershell
eksctl update addon --name vpc-cni --cluster lenie-ai --version latest --wait
```

```powershell
eksctl update addon --name kube-proxy --cluster lenie-ai --version latest --wait
```

## setup EBS support

```powershell
eksctl create iamserviceaccount --name ebs-csi-controller-sa --namespace kube-system --cluster lenie-ai --role-name AmazonEKS_EBS_CSI_DriverRole --role-only --attach-policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy --approve
```
result will be like:

``` powershell
2024-10-23 15:37:20 [ℹ]  1 iamserviceaccount (kube-system/ebs-csi-controller-sa) was included (based on the include/exclude rules)
2024-10-23 15:37:20 [!]  serviceaccounts in Kubernetes will not be created or modified, since the option --role-only is used
2024-10-23 15:37:20 [ℹ]  1 task: { create IAM role for serviceaccount "kube-system/ebs-csi-controller-sa" }
2024-10-23 15:37:20 [ℹ]  building iamserviceaccount stack "eksctl-lenie-ai-addon-iamserviceaccount-kube-system-ebs-csi-controller-sa"
2024-10-23 15:37:21 [ℹ]  deploying stack "eksctl-lenie-ai-addon-iamserviceaccount-kube-system-ebs-csi-controller-sa"
2024-10-23 15:37:21 [ℹ]  waiting for CloudFormation stack "eksctl-lenie-ai-addon-iamserviceaccount-kube-system-ebs-csi-controller-sa"
2024-10-23 15:37:51 [ℹ]  waiting for CloudFormation stack "eksctl-lenie-ai-addon-iamserviceaccount-kube-system-ebs-csi-controller-sa"
```

Add addons by web interface.

```shell
eksctl create addon --cluster lenie-ai --name aws-ebs-csi-driver --version latest \
    --service-account-role-arn arn:aws:iam::008971653395:role/AmazonEKS_EBS_CSI_DriverRole --force
```

## install metric server

Below part is created using description from: https://docs.aws.amazon.com/eks/latest/userguide/metrics-server.html

```shell
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

```shell
kubectl get deployment metrics-server -n kube-system
```

A example output:
```text
NAME             READY   UP-TO-DATE   AVAILABLE   AGE
metrics-server   1/1     1            1           65s

```
Let's check usage of nodes:

```shell
kubectl top nodes
```

An example of output:
```text
NAME                           CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
ip-172-31-2-41.ec2.internal    65m          3%     935Mi           27%
ip-172-31-88-51.ec2.internal   63m          3%     822Mi           24%

```

## installing useful helm charts

### automatic restart of pods after configmap update

```shell 
helm repo add stakater https://stakater.github.io/stakater-charts
```
```text
"stakater" has been added to your repositories
```


```shell
helm repo update
``` 

```text
Hang tight while we grab the latest from your chart repositories...
...Successfully got an update from the "aws-ebs-csi-driver" chart repository
...Successfully got an update from the "eks" chart repository
...Successfully got an update from the "external-secrets" chart repository
...Successfully got an update from the "jaegertracing" chart repository
...Successfully got an update from the "stakater" chart repository
...Successfully got an update from the "grafana" chart repository
...Successfully got an update from the "prometheus-community" chart repository
...Successfully got an update from the "bitnami" chart repository
Update Complete. ⎈Happy Helming!⎈
```
```shell
helm install stakater/reloader --generate-name
```

```text
NAME: reloader-1725536856
LAST DEPLOYED: Thu Sep  5 13:47:39 2024
NAMESPACE: default
STATUS: deployed
REVISION: 1
TEST SUITE: None
NOTES:
- For a `Deployment` called `foo` have a `ConfigMap` called `foo-configmap`. Then add this annotation to main metadata of your `Deployment`
  configmap.reloader.stakater.com/reload: "foo-configmap"

- For a `Deployment` called `foo` have a `Secret` called `foo-secret`. Then add this annotation to main metadata of your `Deployment`
  secret.reloader.stakater.com/reload: "foo-secret"

- After successful installation, your pods will get rolling updates when a change in data of configmap or secret will happen.```

see more: https://github.com/stakater/Reloader
```

## useful commands

### rename context
```shell
kubectl config rename-context iam-root-account@lenie-ai.us-east-1.eksctl.io lenie_ai_dev
```

### setup lenie-ai-dev namespace as default
```shell
kubectl config set-context --current --namespace=lenie-ai-dev
```
```text
Context "lenie_ai_dev" modified.
```

## deleting cluster 

```shell
eksctl delete cluster --name lenie-ai --region us-east-1 --profile lenie_admin
```

The eksctl command will not delete local setup, so you need also:
* delete cluster from kubectl configuration (kubectl config delete-cluster ...)
* delete user from kubectl configuration (kubectl config delete-user ...)
* delete context from kubectl configuration (kubectl config delete-context ...)

