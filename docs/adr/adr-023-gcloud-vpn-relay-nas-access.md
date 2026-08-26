# ADR-023: Google Cloud VPS as OpenVPN relay for remote NAS access

**Date:** 2026-08-14  
**Status:** Accepted — implementation pending  
**Decision makers:** Ziutus

## Context

The Chrome extension (`web_chrome_extension/`) and other remote-access paths
need to reach the NAS (`192.168.200.7`) from outside the home network. The
project has been moving away from AWS toward the NAS as the primary
environment (see `docs/deployment/README.md`), so the old AWS-based access
paths are being retired rather than restored.

A prior attempt used the NAS's native QVPN Service Center as a WireGuard
**server** accepting inbound connections directly (see project memory
`project_qnap_vpn_remote_access`). This was blocked: the home ISP does
carrier-grade NAT (CGNAT) — the WAN IP visible on the router differs from the
public IP visible from outside, so inbound port-forwarding to the router
never reaches it. `myQNAPcloud Link` was evaluated and rejected as a
workaround, since it only reverse-proxies QNAP's web services (File Station
etc.), not generic VPN UDP traffic. The WireGuard server on the NAS is
currently **disabled**.

The only architecture that survives CGNAT without asking the ISP for a
public/static IP is a small relay host with a public IP that the NAS dials
**out** to (outbound connections always traverse CGNAT), which other clients
then connect to. This ADR chooses where that relay runs, what it costs, and
which VPN protocol it uses.

The project previously ran a comparable pattern on AWS: an EC2-based OpenVPN
bastion in front of RDS, plus a separate `ec2-manager` Lambda (start / stop /
status) sitting behind API Gateway with API-key auth, invoked from a simple
static frontend. Both were deleted 2026-07-02 when RDS was decommissioned —
not because the pattern was wrong, but because the thing behind it (RDS)
was gone. Source is kept for reference at
`infra/aws/serverless/lambdas/ec2-manager/lambda_function.py` and
`infra/aws/serverless/CLAUDE.md`.

## Decision

### Cloud provider: Google Cloud, not AWS or a plain VPS

The project already runs a low-priority learning experiment comparing AWS
and GCloud for the main app (`docs/deployment/hyperscalers/aws-gcloud-experiment.md`).
This relay is a small, low-risk place to get hands-on GCloud experience,
separate from that experiment's scope (this ADR is about VPN plumbing, not
about migrating the application). A plain always-on VPS (Hetzner/DigitalOcean/OVH,
considered earlier per project memory) remains a viable fallback — see
Alternatives.

### Compute: e2-micro, started on demand, not run 24/7

Expected usage is 20-30 hours/month. GCE bills per-second while running;
keeping the VM stopped except when in use is the main lever for keeping this
cheap:

- **Machine type:** `e2-micro` — the relay only forwards VPN packets, CPU/RAM
  needs are negligible.
- **Region:** `europe-central2` (Warsaw) — lowest latency to the NAS. The
  GCloud free tier for `e2-micro` only applies in three US regions
  (`us-west1`, `us-central1`, `us-east1`); running in Europe means paying
  the (small) on-demand rate, which is preferred over the latency hit of a
  US region.
- **Disk:** 10 GB `pd-standard` boot disk (minimum for standard images) —
  the relay is stateless (OpenVPN config can be recreated), no need for more.
- **External IP: ephemeral, not static.** Since Feb 2024 Google charges for
  *all* external IPv4 addresses, and a static IP attached to a **stopped**
  instance is billed at a higher "reserved, unused" rate than an IP in use
  on a running instance. At ~95% of the month stopped, a static IP would
  cost more than the VM itself. An ephemeral IP costs nothing while the VM
  is off and only the standard in-use rate while running.

### DNS: Google Cloud DNS, not a third-party DDNS service

An ephemeral IP means the relay's address changes on every start, so clients
need a stable hostname instead of a hardcoded IP. A startup-script on the VM
updates a Cloud DNS record on boot.

- **Cost:** $0.20/month per managed zone + $0.40/million queries — at
  personal-use query volume this rounds to ~$0.20-0.25/month total.
- Chosen over a free third-party DDNS provider (DuckDNS, Cloudflare) for
  consistency: everything stays inside one GCloud project with one IAM
  model, instead of adding another external account/dependency. The cost
  difference (~$0.20/month) is noise.

### VPN protocol: OpenVPN, not WireGuard

WireGuard was the right choice for the earlier (abandoned) design, where the
NAS was the VPN **server** accepting inbound connections — QVPN Service
Center's WireGuard *server* support on this NAS (TS-453Be, QTS 5.2.9) was
confirmed. This design flips the NAS to be a VPN **client** dialing out to
the relay, and QNAP's native outbound VPN client has long-established,
well-documented OpenVPN support; WireGuard client-mode support is newer and
unverified on this NAS/QTS combination.

OpenVPN is chosen because:
- The laptop already has **OpenVPN Connect** installed, from the earlier
  AWS OpenVPN bastion (see `infra/aws/CLAUDE.md`) — no new client software.
- Proven experience with the protocol from that earlier setup.
- OpenVPN can run over TCP/443, which blends in on networks that block
  arbitrary UDP (hotel/public Wi-Fi) — WireGuard is UDP-only.
- Mature, well-documented client-mode (dial-out) support on QNAP QTS.

Trade-off accepted: OpenVPN has somewhat higher overhead and handles
network roaming (Wi-Fi↔LTE) less gracefully than WireGuard. Given this
relay is used 20-30 hours/month, not as a permanent low-latency tunnel,
that trade-off is acceptable.

### Start/stop control: API Gateway + Cloud Function, mirroring the old AWS pattern

Replicates the deleted `ec2-manager` / API Gateway pattern 1:1 rather than a
simplified single-function design:

| AWS (deleted 2026-07-02) | GCloud equivalent |
|---|---|
| Lambda (`ec2-manager`: start/stop/status via `boto3.client('ec2')`) | Cloud Function (2nd gen), same three actions via the Compute Engine Admin API |
| API Gateway + API key | Google Cloud API Gateway + API key (same mechanism: key in a header, restricted to this API in Cloud Console) |
| CloudFront + S3 static frontend | **Firebase Hosting**, not Cloud Storage + Cloud CDN + external HTTP(S) Load Balancer — the GCloud load balancer's fixed forwarding-rule fee (~$18-25/month) would dwarf the entire rest of this budget. Firebase Hosting's free tier gives HTTPS + CDN + custom domain without that cost. |

Considered and rejected: a single Cloud Function doing its own API-key
comparison against a secret, with no API Gateway in front. Cheaper by zero
(both are free at this call volume) and simpler to deploy, but drops the
built-in throttling/quota/key-management that API Gateway gives for free.
Chosen to keep parity with the previously working AWS design rather than
save the (currently unclear) benefit of one less moving part.

### Infrastructure as code: Terraform

Terraform provisions the relay (VM, disk, ephemeral IP, DNS zone/record,
Cloud Function, API Gateway config, Firebase Hosting site, IAM/service
account). No separate ADR for this choice — unlike the AWS
CloudFormation-vs-CDK decision ([ADR-016](adr-016-cloudformation-vs-cdk.md)),
there isn't a real competing alternative to weigh: GCloud's own "Deployment
Manager" is effectively superseded by "Infrastructure Manager", which itself
wraps Terraform under the hood, so Terraform is the natural default rather
than a contested pick. This relay gets its own dedicated GCloud project and
region (`europe-central2`, per the latency reasoning above).

## Estimated monthly cost

| Component | Estimate |
|---|---|
| e2-micro compute, 20-30h/month | ~$0.20-0.36 |
| 10 GB pd-standard disk (billed 24/7 regardless of VM state) | ~$0.48 |
| Ephemeral external IP (billed only while running) | ~$0.10-0.15 |
| Cloud DNS managed zone | ~$0.20-0.25 |
| Network egress (light API/VPN traffic) | ~$0.20-1.50, variable |
| API Gateway, Cloud Function, Firebase Hosting | $0 — within free tier at this call volume |
| **Total** | **~$1-2.5/month (~5-11 zł/month)** |

Prices sourced from GCloud pricing pages/search in August 2026; not
independently verified against the GCloud pricing calculator before this
ADR was written — do that before provisioning.

## Consequences

- Requires a GCloud project/billing account; none is currently provisioned
  for this purpose (the existing `aws-gcloud-experiment.md` document is a
  thought experiment, not a live account) — implementation must set this up.
- Ephemeral IP + DNS-on-boot adds a moving part (startup-script must succeed
  every time the VM starts, or the hostname goes stale) compared to a fixed
  IP; accepted in exchange for avoiding the idle-static-IP cost.
- Introduces Google Cloud as a second cloud provider actively used by the
  project (previously only AWS, now being wound down) — scoped narrowly to
  this relay, not a general migration; does not change the NAS-first
  direction in `docs/deployment/README.md`.
- If this doesn't pan out operationally, the documented fallback is a
  small always-on VPS (Hetzner/DigitalOcean/OVH, ~20-25 zł/month, static IP
  included, no start/stop automation needed) — simpler at the cost of a few
  more zł/month.
- The disabled WireGuard server config in QVPN Service Center on the NAS
  becomes unused; no need to remove it, but it should not be re-enabled as
  part of this work (this ADR replaces that approach, not extends it).

## Addendum (2026-08-26): DNS delegation instead of a full domain move to Cloud DNS

Phase 1 (bare VM + OpenVPN server) was implemented and verified end-to-end 2026-08-25 (PR #583) — see `infra/gcloud/terraform/CLAUDE.md` for what actually shipped and the pitfalls hit along the way.

This ADR's "DNS: Google Cloud DNS" decision assumed `lenie-ai.eu` itself would move to Cloud DNS. In practice `lenie-ai.eu` stays in AWS Route53 (hosted zone `Z07906713RCJHAZLQEP4C`) — it still serves the landing page and backs the DynamoDB page-cache (`infra/aws/CLAUDE.md`), and a full domain move is only planned once those migrate too. Instead:

- `gcloud.lenie-ai.eu` is a new **delegated subdomain**: a zone in Google Cloud DNS (`infra/gcloud/terraform/dns.tf`), with a one-time NS record added manually to the Route53 zone pointing at it. That NS record is the *only* touch of AWS in this whole design — added once via `aws route53 change-resource-record-sets`, deliberately kept out of Terraform (no `aws` provider in the otherwise pure-GCP config).
- Every record under `*.gcloud.lenie-ai.eu` (including `vpn.gcloud.lenie-ai.eu`, the relay's hostname) is served and updated directly through Cloud DNS from then on — no AWS credential exists anywhere in the ongoing automation.
- The DNS record update itself is done by the **VM's own startup-script** on every boot (reads its own ephemeral external IP from the GCP metadata server), not by the start/stop Cloud Function — keeping the Cloud Function free of any DNS concern and scoped to exactly the "Start/stop control" role this ADR originally described for it.

This is a narrower, cheaper deviation than it looks: the "DNS: Google Cloud DNS" section's cost/reasoning (~$0.20-0.25/month per zone) is unaffected, since `gcloud.lenie-ai.eu` is still a Cloud DNS managed zone — only the parent domain's registrar-level authority stays with Route53.

## Open items for implementation

- Verify current GCloud pricing via the official calculator before
  provisioning (see caveat above).
- Confirm QNAP's native outbound VPN client actually supports OpenVPN
  client profiles on this QTS version before building the relay server
  side, so the NAS-side leg of the design is not just assumed.
- Decide the Compute Engine Admin API service-account scope for the Cloud
  Function (least privilege: start/stop/get on this one instance only,
  mirroring the AWS IAM policy the old `ec2-manager` used).
