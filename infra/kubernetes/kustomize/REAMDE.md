
Do zbudowania zasobów kubernetesowych dotyczących lenie-ai wystarczy wykonać polecenie:

```bash
kubectl apply -k overlays/gke/
```

Ustwienie domyślnej namespace pod tą konfiguracje wykonasz:

```bash
kubectl config set-context --current --namespace=lenie-ai-dev
```

Dostęp do bazy danych z poziomu k8s, łączenie się bezpośrednio przez pod:

```bash
kubectl port-forward  pod/lenie-ai-db-0 5432:5432
```

```bash
kubectl exec -it lenie-ai-db-0 -- psql -U pguser lenie-ai
```
