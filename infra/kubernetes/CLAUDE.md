# infra/kubernetes

Kustomize manifests for a **learning** Kubernetes environment (CKA practice, kubeadm first) — see
[ADR-036](../../docs/adr/adr-036-kubernetes-cka-learning-environment.md) and [README.md](README.md). Not deployed on
the NAS; the NAS Compose stack stays the source of truth.

- `base/` must stay distribution-neutral (no StorageClass, registry or Ingress class); put those in `overlays/<cluster>/`.
- Keep it in step with `infra/docker/compose.nas.yaml` when a service's command, env or probes change.
- Real secrets live in git-ignored `*.env` files (only `*.env.example` is tracked); never commit a rendered Secret.
- Validate with `kubectl kustomize overlays/kubeadm` (copy `lenie.env.example` to `lenie.env` first, delete it after).
- The earlier GKE Kustomize/Helm setup is archived at tag `archive/infra-kubernetes`; do not restore it.
