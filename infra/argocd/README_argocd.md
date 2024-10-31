
```shell
argocd repo add https://gitlab.com/ziutus/lenie-server.git --username ziutus --password glpat-XYZ
```

```shell
   argocd app create lenie-ai-server --repo https://gitlab.com/ziutus/lenie-server.git --path infra/kubernetes/lenie/raw --dest-server https://kubernetes.default.svc --dest-namespace lenie-ai-dev
```