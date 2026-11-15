# ADR-036: Kubernetes version of Lenie — a learning environment for CKA, kubeadm first, Kustomize

**Date:** 2026-11-15
**Status:** Accepted
**Decision makers:** Ziutus

## Context

The only deployed environment is Docker Compose on the NAS (`infra/docker/compose.nas.yaml`, see
[docs/deployment/README.md](../deployment/README.md)). An earlier Kustomize + Helm setup for GKE was removed on
2026-07-22 as stale (archived at tag `archive/infra-kubernetes`).

A Kubernetes variant is wanted now for two reasons: to prepare for the **CKA** (Certified Kubernetes
Administrator) exam, and to later compare with **k0s**, which the author uses at work. This is a learning
environment, not a production target — it must not force complexity into the application code
(same rule as the other experiments in `docs/deployment/`).

## Options

1. **kubeadm cluster, 1 control plane + 2 workers, on VMs (chosen first).** The CKA exam runs on kubeadm-built
   clusters: static pods in `/etc/kubernetes/manifests`, `etcdctl snapshot`, `kubeadm upgrade`, kubelet and
   certificate troubleshooting. Three nodes allow practising drain/cordon, rolling upgrades and scheduling.
2. **k0s.** Control-plane components run as processes, etcd is managed by k0s, upgrades go through `k0sctl` — the
   exam skills above would not be practised. Kept for **later**, as a second overlay over the same base.
3. **k3s / kind / k3d.** Convenient, but they hide exactly what the exam asks about (bundled Traefik, ServiceLB,
   local-path, no kubeadm layout).

For manifests: **Kustomize** (in the CKA curriculum, built into `kubectl -k`, `base/` + `overlays/` fits one
application with a few environments) rather than Helm; the application is not a chart for strangers, so templating
adds nothing. Helm is practised separately for the exam, not used for Lenie.

## Decision

- Cluster: kubeadm, 1 control plane + 2 workers on VMs (not on the NAS host that serves the household).
- Manifests in `infra/kubernetes/`: `base/` is distribution-neutral; `overlays/kubeadm/` holds what differs per
  cluster (image registry, StorageClass, Ingress host). `overlays/k0s/` is added later over the same base.
- First vertical slice: PostgreSQL (StatefulSet + PVC), Alembic migration (Job), backend (Deployment), frontend
  (Deployment), Ingress. Workers, `ner_service`, MinIO and the bridges come later.
- Secrets: a plain Kubernetes `Secret` generated from an untracked `*.env` file (`SECRETS_BACKEND=env`). Vault is
  not deployed in the cluster for now.
- Images come from a registry the nodes can reach; the overlay rewrites names/tags with `images:`.

## Consequences

- Positive: exercises the CKA domains on a real workload (storage with PVC, Services/Ingress; NetworkPolicy and RBAC
  can be added on top); manifests stay portable across distributions.
- Negative: a second deployment description to keep in step with `compose.nas.yaml`; the migration Job is immutable,
  so it must be deleted before re-applying with a new image.
- Open: how Vault and the shared volumes (`lenie-document-work`, the Obsidian vault) map to the cluster — decided
  when the workers are added.
