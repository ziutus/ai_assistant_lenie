# GCloud Terraform — VPN relay

Terraform configuration provisioning the OpenVPN relay VM from [ADR-023](../../../docs/adr/adr-023-gcloud-vpn-relay-nas-access.md). **Phase 1 + partial Phase 2**: the VPN server + firewall rule, a delegated Cloud DNS zone that keeps the relay's hostname current across restarts, and a start/stop/status Cloud Function. Still not implemented: a public HTTP endpoint for that function (API Gateway equivalent) and the Firebase Hosting frontend from the ADR — deliberately deferred, see "DNS + start/stop" below.

## Directory Structure

```
terraform/
├── main.tf      # Providers (google ~> 6.27, archive ~> 2.4) + GCS backend config
├── variables.tf # project_id, region, zone (all defaulted)
├── vpn-relay.tf # e2-micro instance running the OpenVPN server
├── firewall.tf  # Opens udp/1194 to 0.0.0.0/0 for the vpn-relay tag
├── dns.tf       # Cloud DNS zone gcloud.lenie-ai.eu + the VM's own DNS-scoped service account
├── function.tf  # vpn-relay-control Cloud Function (start/stop/status) + its instance-scoped service account
├── outputs.tf   # External IP of the relay, Cloud DNS zone name servers
└── data/
    └── openvpn-install-startup.sh  # VM startup-script: installs OpenVPN (once), updates Cloud DNS (every boot)

../functions/vpn-relay-control/     # Cloud Function source (main.py, requirements.txt) - zipped by function.tf's archive_file data source
```

## DNS + start/stop (Phase 2, partial)

**Why cross-cloud DNS instead of just Cloud DNS as the ADR originally assumed:** `lenie-ai.eu` is managed in AWS Route53 (hosted zone `Z07906713RCJHAZLQEP4C`) and stays there — the landing page and the DynamoDB page-cache still live on AWS, and moving the whole domain is only planned once those migrate too. Instead of a full domain move, this uses a classic DNS delegation: `gcloud.lenie-ai.eu` is a zone in **Google Cloud DNS** (`dns.tf`), and the *only* touch of AWS is a one-time NS record in the Route53 zone delegating that one subdomain — added manually via `aws route53 change-resource-record-sets` after `terraform apply` produces the zone's `gcloud_dns_zone_name_servers` output, **not** managed by Terraform (kept out on purpose — no `aws` provider in this otherwise pure-GCP config). Every record under `*.gcloud.lenie-ai.eu` is then served directly by Cloud DNS — the ongoing automation below never touches AWS or holds any AWS credential.

**Who updates the DNS record:** the VM's own startup-script (`data/openvpn-install-startup.sh`), not the Cloud Function. On every boot (not just the first — see the marker-scoping fix below) it reads its own external IP from the GCP metadata server and upserts `vpn.gcloud.lenie-ai.eu` (A, TTL 60s) via `gcloud dns record-sets`, authenticated as the VM's attached service account (`vpn-relay-vm`, `roles/dns.admin` scoped to just this one managed zone — not project-wide). This keeps the Cloud Function itself free of any DNS/cross-cloud concern.

**Fixed bug while adding this:** the original startup-script's `MARKER` file guarded the *entire* script with an early `exit 0` on any boot after the first. Since the boot disk persists across stop/start (the VM isn't recreated), this meant nothing past that line — including the now-added DNS update — would ever run again after the first boot. The marker now only guards the one-time OpenVPN install section; the DNS update runs unconditionally on every boot.

**Cloud Function (`function.tf`):** `vpn-relay-control`, Python 3.12, 2nd gen, mirrors the deleted AWS `ec2-manager` Lambda (`infra/aws/serverless/lambdas/ec2-manager/lambda_function.py`) — same three actions (start/stop/status) via `google-cloud-compute` instead of `boto3`. Its own service account (`vpn-relay-control`) is scoped to start/stop/get on the `lenie-vpn-relay` instance only (IAM Condition on the resource name), not project-wide compute admin. Deployed `--no-allow-unauthenticated` equivalent (no public invoker binding) — invoke via `make gcloud-vpn-start|stop|status` (wraps `gcloud functions call`), not a public URL. API Gateway + Firebase Hosting frontend from the ADR remain future work if ever needed.

**IAM pitfalls hit deploying the Cloud Function for the first time in this project** — this project's default Compute Engine service account (`<project-number>-compute@developer.gserviceaccount.com`, used as the Cloud Build worker identity for 2nd-gen function builds) has **zero project-level IAM roles**: Google stopped auto-granting it `roles/editor` for projects created after mid-2024, so every permission the build pipeline implicitly assumed had to be granted explicitly. All four are in `function.tf`, applied in the order the build actually needs them (each surfaced only after fixing the previous one):

1. `roles/iam.serviceAccountUser` on the `vpn-relay-control` SA, granted to **the identity running `terraform apply`** (`google_client_openid_userinfo` data source, not hardcoded) — 2nd-gen functions deploy via Cloud Run, and the deployer needs `iam.serviceaccounts.actAs` to attach a non-default runtime SA to the Cloud Run service. Without it: `403 ... Permission 'iam.serviceaccounts.actAs' denied`.
2. `roles/storage.objectViewer` on **both** the function's own source bucket (`lenie-ai-478308-gcf-source`) **and** the Cloud-Functions-managed staging bucket (`gcf-v2-sources-<project-number>-<region>`, auto-created on first deploy, legacy-ACL not uniform-bucket-level-access) — the build's `gcs-fetcher` step reads from the *second* bucket, not the one Terraform manages, so granting only the first isn't enough. Without it: build step `fetch` fails with a bare non-zero exit, no readable error message.
3. `roles/artifactregistry.writer` and `roles/logging.logWriter` (project-level) on the same default Compute SA — the buildpack "creator" step pushes the built image to Artifact Registry and needs to write its own logs. Cloud Build silently omits step logs entirely without the logging role (the build result itself contains a `warnings[]` entry naming the missing role — check that field via `gcloud builds describe <id> --format=json`, not `gcloud builds log`, when a build fails with no visible output).
4. **`available_memory = "256Mi"`, not `"128Mi"`** — `google-cloud-compute`'s gRPC client alone uses ~140MiB at cold start, over the default 128Mi limit; the Cloud Run revision fails its startup probe with `Memory limit ... exceeded` (visible via `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="vpn-relay-control"'`).

**If Cloud Function deploys ever start failing again with an opaque `Build failed` / `Could not create or update Cloud Run service` error**, check in this order: `gcloud builds describe <build-id> --format=json` for `warnings[]` and `failureInfo.detail` (names the failing step), then the Cloud Run revision's own logs (`resource.type="cloud_run_revision"`) for anything past a successful build — `gcloud builds log` on its own is frequently empty for buildpack-based 2nd-gen builds and shouldn't be trusted as "no error occurred".

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

# ONE-TIME after the very first apply that creates the Cloud DNS zone: delegate the subdomain
# from Route53. Get the name servers from the terraform output, then in the AWS account that
# manages lenie-ai.eu:
terraform output gcloud_dns_zone_name_servers
aws route53 change-resource-record-sets \
  --hosted-zone-id Z07906713RCJHAZLQEP4C \
  --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"gcloud.lenie-ai.eu","Type":"NS","TTL":172800,"ResourceRecords":[{"Value":"<ns1>"},{"Value":"<ns2>"},{"Value":"<ns3>"},{"Value":"<ns4>"}]}}]}'

# fetch client configs
gcloud compute scp lenie-vpn-relay:/root/nas.ovpn . --zone=europe-central2-a
gcloud compute scp lenie-vpn-relay:/root/demo-laptop.ovpn . --zone=europe-central2-a

# start/stop
make gcloud-vpn-start
make gcloud-vpn-stop
make gcloud-vpn-status
```

## Cost note

The VM still runs until stopped (no scheduled auto-stop) — `make gcloud-vpn-stop` after each demo/session to avoid unnecessary compute charges. See the cost table in the ADR for the on-demand target (~5-11 zł/month at 20-30h use); Cloud DNS adds ~$0.20-0.25/month (managed zone) on top.
