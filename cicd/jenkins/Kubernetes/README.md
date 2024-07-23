
# Source of code
The base description for this setup is taken from https://codefresh.io/learn/jenkins/running-jenkins-on-kubernetes-pros-cons-and-a-quick-tutorial/ and has been adopted for 'Docker-desktop' and AWS solution.

# Docker-Desktop

```
kubectl create namespace devops-tool-suite
```

# AWS

## Login to SSO

```powershell
aws sso login --profile odkrywca-dev1-Administrator
```

## Using eksctl to install Kubernetes cluster
```powershell
eksctl create cluster -f aws_eksctl.yaml
```

````powershell
helm repo add eks https://aws.github.io/eks-charts
````

```powershell
helm repo update eks
```

```powershell
aws eks describe-cluster --name eks-jenkins-demo --region eu-east-1 --query "cluster.resourcesVpcConfig.vpcId" --output text --profile odkrywca-dev1-Administrator
```

```powershell
helm install aws-load-balancer-controller eks/aws-load-balancer-controller --namespace kube-system --set clusterName=eks-jenkins-demo --set serviceAccount.create=false --set region=eu-west-1 --set vpcId=vpc-0e91984d3dba0df6b --set serviceAccount.name=aws-load-balancer-controller
```

```powershell
aws eks update-kubeconfig --region eu-west-1 --name eks-jenkins-demo --profile odkrywca-dev1-Administrator
```

## Testing Karpenter

```powershell
kubectl apply -f karpenter_test.yaml
kubectl scale deployment inflate --replicas 5
kubectl logs -f -n "${KARPENTER_NAMESPACE}" -l app.kubernetes.io/name=karpenter -c controller
kubectl delete deployment inflate
kubectl logs -f -n "${KARPENTER_NAMESPACE}" -l app.kubernetes.io/name=karpenter -c controller
```

## Cleaning 

```powershell
 eksctl delete cluster --name eks-jenkins-demo --profile odkrywca-dev1-Administrator
```