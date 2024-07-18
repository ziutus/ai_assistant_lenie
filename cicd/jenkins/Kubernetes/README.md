
# Source of code
The base description for this setup is taken from https://codefresh.io/learn/jenkins/running-jenkins-on-kubernetes-pros-cons-and-a-quick-tutorial/ and has been adopted for 'Docker-desktop' and AWS solution.

# Docker-Desktop

```
kubectl create namespace devops-tool-suite
```

# AWS

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
aws eks describe-cluster --name eks-dev3 --region us-east-1 --query "cluster.resourcesVpcConfig.vpcId" --output text
```

```powershell
helm install aws-load-balancer-controller eks/aws-load-balancer-controller --namespace kube-system --set clusterName=eks-dev3 --set serviceAccount.create=false --set region=us-east-1 --set vpcId=vpc-0af37773948b5835e --set serviceAccount.name=aws-load-balancer-controller
```

## Cleaning 

```powershell
 eksctl delete cluster --name eks-dev3
```