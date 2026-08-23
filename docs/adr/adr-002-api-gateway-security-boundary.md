# ADR-002: API Gateway as Security Boundary (No NAT Gateway)

**Date:** 2025 (initial AWS architecture)
**Status:** Accepted (dormant — see note)

> **Note (2026-08-22):** The API Gateway/Lambda infrastructure described here was decommissioned on 2026-07-02. Only the `/url_add` Lambda remains, kept for the Chrome extension path; the main API now runs as Flask behind the NAS Docker Compose stack. See `docs/deployment/README.md` and `docs/aws-serverless-restoration.md`.

### Context

The system needed internet-facing API access for mobile devices (Chrome extension on phone/tablet) while keeping infrastructure costs minimal (hobby project, $8/month budget target).

### Decision

Use AWS API Gateway as the single entry point with API key authentication. No NAT Gateway (saves ~$30/month). Lambda functions split into VPC (database access) and non-VPC (internet access) to work around the missing NAT Gateway.

### Consequences

- **Positive:** Fully managed TLS, throttling, DDoS protection. No servers to patch.
- **Positive:** ~$30/month saved on NAT Gateway.
- **Negative:** Lambda functions must be split between VPC and non-VPC, adding architectural complexity.
- **Negative:** Some endpoints exist only in `server.py` (Docker/K8s) and not in Lambda.
