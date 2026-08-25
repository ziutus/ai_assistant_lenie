# GCloud Terraform — VPN relay

Terraform configuration provisioning the OpenVPN relay VM from [ADR-023](../../../docs/adr/adr-023-gcloud-vpn-relay-nas-access.md). This is **Phase 1 only**: the bare VPN server + firewall rule. Cloud DNS, the start/stop API Gateway + Cloud Function, and the Firebase Hosting frontend from the ADR are not implemented yet.

## Directory Structure

```
terraform/
├── main.tf      # Provider (google ~> 6.27) + GCS backend config
├── variables.tf # project_id, region, zone (all defaulted)
├── vpn-relay.tf # e2-micro instance running the OpenVPN server
├── firewall.tf  # Opens udp/1194 to 0.0.0.0/0 for the vpn-relay tag
├── outputs.tf   # External IP of the relay
└── data/
    └── openvpn-install-startup.sh  # VM startup-script, installs OpenVPN non-interactively
```

## Provider / State

- **Project**: `lenie-ai-478308` (existing project, not a new dedicated one — user's deliberate choice, deviates from the ADR's "independent project" note).
- **Region/zone**: `europe-central2` / `europe-central2-a` (Warsaw — lowest latency to the NAS).
- **State backend**: GCS bucket `gs://lenie-ai-478308-tfstate` (prefix `vpn-relay`), versioning enabled. Chosen over local state (unlike `infra/aws/terraform/`) so `terraform apply`/`destroy` is safe to run from any machine/worktree, not tied to one disk. The bucket itself is **not** managed by this Terraform config (created once manually via `gcloud storage buckets create`, since a backend can't provision its own storage).
- Auth: `gcloud auth application-default login` (separate credential store from `gcloud auth login`) must be run once before `terraform init`.

## OpenVPN install

The startup script (`data/openvpn-install-startup.sh`) installs OpenVPN via [angristan/openvpn-install](https://github.com/angristan/openvpn-install), pulled fresh from GitHub at boot time (current version is fully CLI-flag driven, no interactive prompts when flags are given). It creates two clients: `nas` (for the NAS's OpenVPN client/dial-out profile) and `demo-laptop` (for testing external access). Output logged to `/var/log/openvpn-relay-startup.log` on the instance.

**`--tls-sig crypt` (static key), not the installer's default `crypt-v2` (per-session dynamic key)** — QNAP QVPN Service Center's OpenVPN client cannot renegotiate `crypt-v2` on its own automatic ping-restart reconnect (fails with `TLS Error: could not determine wrapping`), so the connection silently dies every ~4 minutes and needs a manual disconnect/reconnect in the QTS UI. The static key removes the renegotiation step; auto-reconnect confirmed working live 2026-08-25. If you ever regenerate a client `.ovpn` by hand (e.g. via `client add` over SSH) it picks up the server's current mode automatically — the script reads `server.conf`, no manual key-swapping needed.

**Routing to `192.168.200.0/24` (the NAS's LAN)** is baked into the startup script, not the ADR's `--local-network` flag — that flag is for networks behind the *server*, but this subnet sits behind a *client* (the NAS). The script instead writes `ccd/nas` (`iroute` + `push-reset`, so the NAS keeps its own default gateway instead of full-tunneling through GCP) and appends a matching `route` line to `server.conf`. It also punches a hole in the installer's default firewall, which otherwise rejects VPN clients reaching any RFC1918 range including this one.

**Confirmed working** (2026-08-25, live test): NAS dialed out via QVPN Service Center → relay → HTTP request from the relay reached the NAS's Lenie backend (`192.168.200.7:5055`) and got a real application response. ICMP (ping) to the NAS is unreliable through the tunnel — irrelevant to the actual use case, don't use it to judge whether the tunnel is up; use a TCP/HTTP check instead.

## Usage

```bash
gcloud auth application-default login   # once
cd infra/gcloud/terraform
terraform init
terraform plan
terraform apply

# fetch client configs
gcloud compute scp lenie-vpn-relay:/root/nas.ovpn . --zone=europe-central2-a
gcloud compute scp lenie-vpn-relay:/root/demo-laptop.ovpn . --zone=europe-central2-a

# stop when not demoing — no start/stop automation exists yet
gcloud compute instances stop lenie-vpn-relay --zone=europe-central2-a
```

## Cost note

Unlike the ADR's on-demand design, this VM runs continuously until manually stopped (Phase 1 has no start/stop automation). Stop it after each demo/session to avoid unnecessary compute charges — see the cost table in the ADR for the on-demand target (~5-11 zł/month at 20-30h use).
