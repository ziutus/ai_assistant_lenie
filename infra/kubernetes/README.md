# Lenie on Kubernetes (learning environment)

A Kubernetes variant of Lenie for **CKA practice** — not a production target and not deployed anywhere real.
Decision and reasoning: [ADR-036](../../docs/adr/adr-036-kubernetes-cka-learning-environment.md). The deployed
environment remains the NAS Compose stack (`infra/docker/compose.nas.yaml`).

## Layout

```
base/               distribution-neutral manifests (namespace `lenie`), one directory per service
  namespace.yaml
  postgres/         headless Service + StatefulSet (PVC via volumeClaimTemplates)
  migrate/          the Alembic migration Job
  backend/          Service + Deployment
  frontend/         Service + Deployment
overlays/kubeadm/   what differs per cluster: image registry, StorageClass, Ingress, Secret
```

Each service directory has its own `kustomization.yaml`, and `base/kustomization.yaml` references the directories
(a base made of bases). Build one service alone, e.g. `kubectl kustomize base/backend`. Ingress, Secret and
StorageClass live in the overlay on purpose — they are cluster-specific.

`overlays/k0s/` is planned over the same `base/` (after the exam).

## First slice (what `base/` contains)

| Object | From compose service |
|---|---|
| StatefulSet + headless Service `lenie-ai-db` | `lenie-ai-db` |
| Job `lenie-migrate` (`alembic upgrade heads`) | `lenie-migrate` |
| Deployment + Service `lenie-ai-server` (probes `/startup`, `/readiness`, `/liveness`) | `lenie-ai-server` |
| Deployment + Service `lenie-ai-frontend` | `lenie-ai-frontend` |

Not yet ported: workers, `ner_service`, MinIO, Vault, the WhatsApp/Obsidian bridges, app2, MCP. Open questions
(Vault, shared volumes) are listed in the ADR.

## Prerequisites in the cluster

- A default or named StorageClass (the overlay patches `local-path` — change it to what `kubectl get sc` shows).
- An Ingress controller with class `nginx`.
- A registry reachable from every node, holding the `lenie-ai-db`, `lenie-ai-server` and `lenie-ai-frontend` images.
  Edit `images:` in `overlays/kubeadm/kustomization.yaml`.

## Deploy

```bash
cd infra/kubernetes/overlays/kubeadm
cp lenie.env.example lenie.env        # git-ignored; set a real POSTGRESQL_PASSWORD
kubectl kustomize .                   # render and review
kubectl apply -k .
kubectl -n lenie get pods,pvc,ingress
```

The frontend is at `http://lenie.k8s.lan`, the API at `http://api.lenie.k8s.lan` — set the API URL in the UI to the
latter. Both names must resolve to the Ingress address.

The migration Job is immutable: before re-applying with a new image, run `kubectl -n lenie delete job lenie-migrate`.

## Exercises worth doing on this workload (CKA domains)

Storage: drop the StatefulSet pod and check the PVC survives · Networking: add a NetworkPolicy allowing only the
backend to reach Postgres · RBAC: a read-only ServiceAccount for the namespace · Scheduling: taint a worker, add
tolerations/affinity · Troubleshooting: break the Secret or the image tag and diagnose from events and logs ·
Cluster: etcd snapshot/restore, `kubeadm upgrade`, drain/cordon while the stack runs.
