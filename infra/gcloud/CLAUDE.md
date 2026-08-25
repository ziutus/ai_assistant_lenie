# Google Cloud Infrastructure

Currently a single purpose: the OpenVPN relay from [ADR-023](../../docs/adr/adr-023-gcloud-vpn-relay-nas-access.md), which lets remote clients (Chrome extension, laptop away from home) reach the NAS (`192.168.200.7`) despite the home ISP's CGNAT. See [`terraform/CLAUDE.md`](terraform/CLAUDE.md) for what's actually deployed — currently **Phase 1 only** (bare VM + OpenVPN server, no DNS/start-stop automation/frontend yet).

This directory previously held an older, unrelated Terraform setup (`cloud-run-shell`, `terraform-server` — a full app-hosting experiment predating the NAS-first architecture) that was removed 2026-07-22 as stale; archived at git tag `archive/infra-gcloud`. The current content is a fresh start, scoped narrowly to the VPN relay — not a revival of that experiment.

## Directory Structure

```
gcloud/
├── CLAUDE.md
└── terraform/        # VPN relay VM — see terraform/CLAUDE.md
```
