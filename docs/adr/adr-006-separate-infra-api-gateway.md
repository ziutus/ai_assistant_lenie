# ADR-006: Separate Infrastructure API Gateway from Application API Gateway

**Date:** 2026-02 (Sprint 3)
**Status:** Accepted
**Decision Makers:** Ziutus

### Context

The AWS deployment had 4 API Gateways:
1. `lenie_split` (1bkc3kz7c9) — main app API from `api-gw-app.yaml`, containing 18 endpoints (10 app + 8 infra)
2. `lenie_dev_infra` (px1qflfpha) — infra API from `api-gw-infra.yaml`, with 7 infra endpoints under different paths
3. `lenie_dev_add_from_chrome_extension` (61w8tmmzkh) — UNUSED duplicate Chrome ext API from `api-gw-url-add.yaml`
4. `lenie_dev_add_from_chrome_extension` (jg40fjwz61) — USED Chrome ext API from `url-add.yaml`

Problems: (A) infrastructure endpoints were duplicated across `api-gw-app` and `api-gw-infra` with inconsistent paths and HTTP methods, (B) two Chrome extension APIs existed where only one was used, (C) the infra API paths (`/database/status`, `/vpn-server/start`) did not match what the frontend expected (`/infra/database/status`, `/infra/vpn_server/start`).

### Decision

1. **Remove the unused Chrome extension API Gateway** (`api-gw-url-add.yaml`) from deployment by commenting it out in `deploy.ini`.
2. **Consolidate all infrastructure endpoints into `api-gw-infra.yaml`** with paths matching frontend expectations (`/infra/database/*`, `/infra/vpn_server/*`, `/infra/sqs/size`, `/infra/git-webhooks`).
3. **Remove all `/infra/*` endpoints from `api-gw-app.yaml`**, leaving only the 10 application endpoints.
4. **Add `infraApiUrl` to the React frontend** so that in AWS Serverless mode, infrastructure calls go to the dedicated infra API Gateway while app calls go to the app API Gateway. In Docker mode, both use the same URL.

### Rationale

1. **Platform consistency.** Infrastructure management (RDS start/stop, EC2, SQS) is AWS-specific and does not exist in Docker/K8s deployments. Keeping infra endpoints separate means `api-gw-app.yaml` defines the same API surface as Docker and K8s, following the project principle of platform-similar deployments.

2. **Single source of truth.** Having the same endpoints in two API Gateways creates confusion about which one is authoritative and risks configuration drift.

3. **Independent lifecycle.** Infrastructure and application endpoints can be deployed and updated independently.

### Consequences

- **Positive:** `api-gw-app.yaml` now matches the Docker/K8s API surface exactly (10 endpoints).
- **Positive:** No duplicate infrastructure endpoints across APIs.
- **Positive:** `api-gw-infra.yaml` paths now match what the frontend sends.
- **Negative:** Frontend needs two API URLs in AWS mode (added `infraApiUrl` to authorization context).
- **Negative:** Requires coordinated deployment (both templates + stack deletion).

### Related Artifacts

- `infra/aws/cloudformation/templates/api-gw-app.yaml` — 10 app endpoints only
- `infra/aws/cloudformation/templates/api-gw-infra.yaml` — 7 infra endpoints (database start/stop/status, vpn start/stop/status, sqs size)
- `web_interface_react/src/modules/shared/context/authorizationContext.js` — `infraApiUrl` state
- `web_interface_react/src/modules/shared/hooks/useDatabase.js` — uses `infraApiUrl` for AWS mode
- `web_interface_react/src/modules/shared/hooks/useVpnServer.js` — uses `infraApiUrl` for AWS mode
- `web_interface_react/src/modules/shared/hooks/useSqs.js` — uses `infraApiUrl` for AWS mode
