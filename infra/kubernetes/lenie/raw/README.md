
```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f lenie_1_namespace.yaml
```

```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f lenie_2_server_configmap.yaml
```

```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f lenie_3_server_secrets.yaml
```

```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f lenie_6_server_deployment.yml
```

```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f lenie_7_server_service.yml
```

```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f lenie_8_client_deployment.yml
```

```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f lenie_9_client_service.yml 
```

```shell
cd /mnt/c/Users/ziutus/git/_lenie-all/ai_assistant_lenie_server/infra/kubernetes/lenie/raw
kubectl apply -f 
```

```text
apiVersion: v1
kind: Pod
metadata:
  name: lenie-ai-server
  namespace: lenie-ai-dev
spec:
  containers:
  - name: lenie-ai-server
    image: linuxexpertpl/lenie-ai-server:0.2.9
    ports:
    - containerPort: 5000
    envFrom:
    - configMapRef:
        name: env-config
    - secretRef:
        name: env-secret
```

```text
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: lenie-ai-server-rs
  namespace: lenie-ai-dev
spec:
  replicas: 2
  selector:
    matchLabels:
      pod-label: lenie-ai-server
  template:
    metadata:
      labels:
        pod-label: lenie-ai-server
    spec:
      containers:
      - name: lenie-ai-server
        image: linuxexpertpl/lenie-ai-server:0.2.6.1
        ports:
        - containerPort: 5000
        envFrom:
        - configMapRef:
            name: env-config
        - secretRef:
            name: env-secret
```