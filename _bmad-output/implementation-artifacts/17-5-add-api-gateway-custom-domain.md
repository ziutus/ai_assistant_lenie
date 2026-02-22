# Story 17.5: Add API Gateway Custom Domain

Status: done

## Story

As a **developer**,
I want API Gateway endpoints accessible through a custom domain `api.dev.lenie-ai.eu` instead of auto-generated AWS execute-api URLs,
so that API consumers have stable, memorable URLs that survive API Gateway recreation and follow the project's domain naming convention.

## Backlog Item

B-15: Add custom domains for API Gateways

## Acceptance Criteria

1. **Given** the project uses two API Gateways (app and infra)
   **When** the developer creates `api-gw-custom-domain.yaml` CloudFormation template
   **Then** the template provisions:
   - ACM certificate for `api.dev.lenie-ai.eu` with DNS validation
   - API Gateway DomainName resource (REGIONAL endpoint, TLS 1.2)
   - BasePathMapping: root path (`/`) → app API Gateway (v1 stage)
   - BasePathMapping: `/infra` → infra API Gateway (v1 stage)
   - Route53 A-record alias pointing to the API Gateway domain
   - SSM parameter exports for cross-stack references

2. **Given** the custom domain is deployed
   **When** a client sends a request to `https://api.dev.lenie-ai.eu/website_list`
   **Then** the request routes to the app API Gateway (same as previous `execute-api` URL with `/v1/website_list`)

3. **Given** the custom domain is deployed
   **When** a client sends a request to `https://api.dev.lenie-ai.eu/infra/sqs/size`
   **Then** the request routes to the infra API Gateway (same as previous `execute-api` URL with `/v1/infra/sqs/size`)

4. **Given** the custom domain uses BasePathMappings
   **When** clients use the new URLs
   **Then** no `/v1` stage prefix is needed (the mapping handles it)

5. **Given** the `url-add.yaml` Lambda template previously had its own REST API Gateway
   **When** the developer consolidates it
   **Then** `url-add.yaml` is fully removed from the codebase
   **And** the `/url_add` endpoint continues to work via `api-gw-app` (consolidated in Sprint 4)
   **And** the post-consolidation state is 2 REST APIs in AWS (app + infra), down from 3

6. **Given** the parameter file `api-gw-custom-domain.json` is created
   **When** it contains `HostedZoneId` and `BaseDomainName` parameters
   **Then** it references the `dev.lenie-ai.eu` hosted zone in Route53

## Implementation Notes

- New template: `infra/aws/cloudformation/templates/api-gw-custom-domain.yaml`
- New parameters: `infra/aws/cloudformation/parameters/dev/api-gw-custom-domain.json`
- Custom domain URLs (no /v1 stage prefix):
  - `https://api.dev.lenie-ai.eu/website_list` (app API)
  - `https://api.dev.lenie-ai.eu/infra/sqs/size` (infra API)
- `url-add.yaml` removed — its REST API Gateway is no longer needed
- CLAUDE.md docs updated to reflect custom domain and template count changes
- ACM certificate managed via CloudFormation (partially addresses B-8)

## Files Changed

- `infra/aws/cloudformation/templates/api-gw-custom-domain.yaml` (new, 123 lines)
- `infra/aws/cloudformation/parameters/dev/api-gw-custom-domain.json` (new)
- `infra/aws/cloudformation/templates/url-add.yaml` (deleted — 131 lines removed)
- `infra/aws/CLAUDE.md` (updated)
- `infra/aws/cloudformation/CLAUDE.md` (updated)

## Commit

`afd4ae0` — feat: add API Gateway custom domain api.dev.lenie-ai.eu with base path mappings
