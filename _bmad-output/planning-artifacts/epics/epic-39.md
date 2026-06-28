## Epic 39: Cloudflare Infrastructure — Domain, Tunnel & MCP Server Portal

The MCP server on NAS is reachable from the public internet via a dedicated Cloudflare-managed domain, HTTPS-encrypted Cloudflare Tunnel, and Zero Trust OAuth authentication through Cloudflare MCP Server Portal — without exposing any NAS ports directly.

**Stories:** 39-1, 39-2, 39-3

Implementation notes:
- Story 39-1 (domain + Cloudflare DNS) must be completed first — Tunnel and MCP Portal require a Cloudflare-managed zone
- Story 39-2 (Cloudflare Tunnel) depends on 39-1
- Story 39-3 (MCP Server Portal / Zero Trust) depends on 39-2 being operational
- All Cloudflare steps are done via the Cloudflare dashboard (GUI) and `cloudflared` CLI — no Terraform/IaC in MVP
- Cloudflare MCP Server Portal is in Open Beta (as of 2026-04); behaviour may differ from docs — fallback documented in Story 39-3

### Story 39.1: Dedicated Domain Registration & Cloudflare DNS Setup

As a **developer**,
I want a dedicated low-cost domain managed entirely by Cloudflare DNS,
so that the MCP server has a stable public hostname without impacting the existing `lenie-ai.eu` production domain on AWS Route53.

**Acceptance Criteria:**

**Given** the developer registers a new domain (~3 EUR/year)
**When** the domain is added to Cloudflare (or registered directly via Cloudflare Registrar)
**Then** Cloudflare is the authoritative DNS provider for that domain (nameservers updated at registrar)

**Given** the domain is managed by Cloudflare
**When** a subdomain `mcp.<domain>` is created
**Then** a CNAME record pointing to the Cloudflare Tunnel endpoint is added (done automatically in Story 39-2)

**Given** the domain setup is complete
**When** the DNS propagation check is run (`dig NS <domain>`)
**Then** Cloudflare nameservers are returned

**Given** `lenie-ai.eu` is hosted on AWS Route53
**When** the new domain is set up
**Then** `lenie-ai.eu` DNS configuration is NOT modified — zero blast radius on production

**Technical notes:**
- Domain cost: ~3 EUR/year (.eu, .com.pl, or similar) — Cloudflare Registrar or third-party (Porkbun, Namecheap)
- Document the chosen domain name in `infra/cloudflare/README.md` (create file)

### Story 39.2: Cloudflare Tunnel Configuration

As a **developer**,
I want a Cloudflare Tunnel connecting NAS to Cloudflare's network,
so that the MCP server is reachable via HTTPS without opening firewall ports on the NAS or home network.

**Acceptance Criteria:**

**Given** `cloudflared` is installed on NAS (as a Docker container)
**When** `cloudflared tunnel login` and `cloudflared tunnel create lenie-mcp` are run
**Then** a tunnel is created in the Cloudflare dashboard and credentials file is saved to NAS filesystem

**Given** the tunnel is created
**When** a route is added: `cloudflared tunnel route dns lenie-mcp mcp.<domain>`
**Then** a CNAME record is created in Cloudflare DNS for `mcp.<domain>` pointing to `<tunnel-id>.cfargotunnel.com`

**Given** a tunnel config YAML exists at the Docker volume equivalent of `/etc/cloudflared/config.yml`:
```yaml
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/<tunnel-id>.json
ingress:
  - hostname: mcp.<domain>
    service: http://lenie-mcp-server:8080
  - service: http_status:404
```
**When** the `cloudflared` container starts
**Then** tunnel connects to Cloudflare and status shows `healthy`

**Given** the tunnel is running
**When** `curl https://mcp.<domain>/health` is run from an external network
**Then** it returns HTTP 200 with `{"status": "ok", ...}`

**Given** `cloudflared` container is added to `compose.nas.yaml`
**When** inspected
**Then** it uses `restart: unless-stopped`, mounts credentials as a Docker volume, and is excluded from git via `.gitignore`

**Technical notes:**
- `cloudflared` Docker image: `cloudflare/cloudflared:latest`
- Container communicates with `lenie-mcp-server` via `lenie-net` Docker network using container name as hostname
- Tunnel credentials (`<tunnel-id>.json`) contain a secret token — must NOT be committed to git
- Add `infra/cloudflare/config.yml.example` with placeholder values as committed reference

### Story 39.3: Cloudflare MCP Server Portal — Zero Trust OAuth

As a **developer**,
I want Cloudflare MCP Server Portal to enforce OAuth authentication before any request reaches the MCP server,
so that the server is only accessible to authenticated users — no direct access possible.

**Acceptance Criteria:**

**Given** Cloudflare Zero Trust is configured for the account
**When** a new "MCP Connector" application is created in Cloudflare Zero Trust → Access → Applications
**Then** the application is configured with:
  - Protected URL: `https://mcp.<domain>/`
  - Identity provider: Google OAuth (or other configured IdP)
  - Policy: allow only `krzysztof@itsnap.eu`

**Given** the Access application is configured
**When** an unauthenticated request is made to `https://mcp.<domain>/mcp`
**Then** Cloudflare redirects to the identity provider login page
**And** the MCP server container does NOT receive the request

**Given** the authenticated session exists
**When** a request is made to `https://mcp.<domain>/mcp`
**Then** the request reaches the MCP server and returns a valid MCP response

**Given** Cloudflare MCP Server Portal is used (Open Beta feature)
**When** the MCP Connector is created in the Cloudflare dashboard
**Then** Cloudflare generates a connector URL usable in Claude Custom Connector configuration (Epic 40, Story 40-2)

**Fallback scenario (if MCP Server Portal feature is unavailable or non-functional):**
**Given** the Open Beta feature does not work as expected
**When** the developer implements the fallback
**Then** authentication is enforced using standard Cloudflare Access (JWT-based) at the Tunnel level
**And** this fallback is documented in `infra/cloudflare/README.md`

**Given** the security configuration is complete
**When** the developer performs a security verification
**Then** attempting to access `https://mcp.<domain>/mcp` without authentication returns a redirect to the identity provider
**And** no NAS ports (8080, 5432, etc.) are exposed to the public internet

**Technical notes:**
- Cloudflare MCP Server Portal is a distinct product from standard Cloudflare Access (Open Beta as of April 2026)
- If MCP Server Portal requires a specific transport format, verify compatibility with FastMCP's SSE output (NFR12)
- NFR4 (HTTPS), NFR7 (Zero Trust OAuth), NFR8 (no direct port exposure) are all verified by this story
