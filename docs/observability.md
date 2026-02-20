# Observability Strategy — Lenie Server 2025

> Last updated: 2026-02-18 | Version: 0.3.13.0

This document describes the project's logging, tracing, and monitoring strategy across all deployment environments (AWS, Docker/local, Kubernetes, GCloud). It serves as the standard for current observability practices and a reference for future improvements.

**Note:** Source file line numbers referenced in this document were verified against version 0.3.13.0 and may drift with future code changes.

## Table of Contents

- [Current State](#current-state)
- [Logging Standards](#logging-standards)
- [Per-Environment Configuration](#per-environment-configuration)
- [Tools Inventory](#tools-inventory)
- [Request Audit Trail](#request-audit-trail)

---

## Current State

The project has **minimal and fragmented observability**. Logging exists in most application components but lacks consistency — no structured logging (JSON), no request ID tracking, and no correlation IDs.

### Backend Logging (`backend/`)

| Component | File | Log Level | Format | Structured? |
|-----------|------|-----------|--------|-------------|
| Flask server | `server.py:7,18` | INFO | Default Python (`logging.basicConfig`) | No |
| YouTube processing | `library/youtube_processing.py:5` | N/A (module logger) | Default Python | No |
| Language detection | `library/text_detect_language.py:5` | N/A (module logger) | Default Python | No |
| YouTube file | `library/stalker_youtube_file.py:11` | N/A (module logger) | Default Python | No |
| Batch: youtube_add | `youtube_add.py:37` | Configurable (DEBUG/INFO via `-v` flag) | `%(asctime)s %(levelname)s %(name)s: %(message)s` | No |
| Batch: do_the_needful | `web_documents_do_the_needful_new.py:22` | INFO | Default Python | No |
| Batch: md_decode | `webdocument_md_decode.py:20-21` | DEBUG | Default Python | No |
| Batch: regexp_by_ai | `webdocument_prepare_regexp_by_ai.py:21-22` | INFO | Default Python | No |

**Key finding:** No structured logging (JSON), no request ID tracking, no correlation IDs anywhere in the backend.

### Lambda Function Logging

| Lambda | File | Logging? | Format | Notes |
|--------|------|----------|--------|-------|
| sqs-weblink-put-into | `lambdas/sqs-weblink-put-into/lambda_function.py:7-10` | YES | Python logger (INFO) | Best practice — comprehensive logging (56 calls), logs data received, S3 uploads, DynamoDB/SQS operations |
| sqs-into-rds | `lambdas/sqs-into-rds/lambda_function.py:3-6` | YES | Python logger (INFO) | Logs events, URL checks, document additions |
| app-server-db | `lambdas/app-server-db/lambda_function.py:2,13` | YES | Python basicConfig (DEBUG) | Extensive but unstructured |
| app-server-internet | `lambdas/app-server-internet/lambda_function.py:4,11` | YES | Python basicConfig (DEBUG) | Basic debug/error |
| rds-start | `lambdas/rds-start/lambda_function.py` | **NO** | print() only | No structured logging — uses print statements and exception handling |
| rds-stop | `lambdas/rds-stop/lambda_function.py` | **NO** | print() only | No structured logging — uses print statements and exception handling |
| rds-status | `lambdas/rds-status/lambda_function.py` | **NO** | print() only | No structured logging — exception handling with pass |
| ec2-start | `lambdas/ec2-start/lambda_function.py` | **NO** | print() only | Uses print for success/error |
| ec2-stop | `lambdas/ec2-stop/lambda_function.py` | **NO** | print() only | Uses print statements |
| ec2-status | `lambdas/ec2-status/lambda_function.py` | **NO** | print() only | Uses print statements |
| sqs-size | `lambdas/sqs-size/lambda_function.py` | **NO** | N/A | Custom generate_response() helper, exception handling only |

**Key finding:** 7 infrastructure Lambdas have no proper logging — they use `print()` statements or no output at all. Application/document-processing Lambdas have proper Python logging.

### CloudFormation-Level Observability

| Resource | Template | Configuration | Status |
|----------|----------|--------------|--------|
| API Gateway app stage | `api-gw-app.yaml:589-598` | TracingEnabled: true, LoggingLevel: INFO, MetricsEnabled: true, DataTraceEnabled: true | **Active** (codified in Story 11-10) |
| API Gateway infra Lambdas | `api-gw-infra.yaml:54-57` | LoggingConfig: JSON format, INFO level (ApplicationLogLevel + SystemLogLevel) | **Active** — Lambda-level structured logging |
| API Gateway infra stage | `api-gw-infra.yaml` | No StageDescription logging | **Not configured** |
| API Gateway url-add | `api-gw-url-add.yaml` | No stage logging/tracing | **Not configured** |
| Step Function | `sqs-to-rds-step-function.yaml` | CloudWatch execution monitoring | **Active** |

**Warning:** `DataTraceEnabled: true` on the app API Gateway logs full request/response bodies to CloudWatch. Review this setting before enabling in production environments with sensitive data.

### Kubernetes Health Probes

Health probes are configured consistently across both Helm and Kustomize deployments:

| Probe | Path | Port | Initial Delay | Period |
|-------|------|------|---------------|--------|
| startupProbe | `/startup` | 5000 | 5s | 10s |
| readinessProbe | `/readiness` | 5000 | 10s | 10s |
| livenessProbe | `/liveness` | 5000 | 10s | 30s |

Sources:
- Helm: `infra/kubernetes/helm/lenie-ai-server/values.yaml:99-116`
- Kustomize: `infra/kubernetes/kustomize/base/server/server_deployment.yml:44-61`

### Frontend Monitoring

All frontend applications currently have **no client-side monitoring or error tracking**:

| Application | Type | Monitoring | Notes |
|-------------|------|-----------|-------|
| Main Frontend (`web_interface_react/`) | React 18 SPA | None | No error tracking, no performance monitoring |
| Add URL App (`web_add_url_react/`) | React 18 SPA | None | Minimal single-page app |
| Browser Extension (`web_chrome_extension/`) | Chrome Extension (Manifest v3) | None | No telemetry |

AWS RUM (Real User Monitoring) was previously integrated but was completely removed in Story 5-2 as dead/unused code. No replacement has been implemented.

### Environments Summary

| Environment | Logging | Tracing | Metrics | Monitoring |
|-------------|---------|---------|---------|------------|
| **AWS Lambda** | CloudWatch (JSON via CF LoggingConfig for infra Lambdas — code still uses print(); basic Python logging for app Lambdas) | X-Ray on API GW app only | CloudWatch built-in | CloudWatch alarms (none configured) |
| **Docker/local** | stdout/stderr (Python logging) | None | `/metrics` stub (returns 500 — view returns None) | None |
| **Kubernetes** | stdout/stderr (Python logging) | None | `/metrics` stub (returns 500), health probes (startup, readiness, liveness) | None |
| **GCloud** | Future: Cloud Logging | Future | Future | Future |

---

## Logging Standards

This section defines the target logging conventions for new and updated code. Existing code does not yet follow these standards — migration would be a separate effort.

### Log Level Conventions

| Level | When to Use | Examples |
|-------|------------|---------|
| **DEBUG** | Detailed diagnostic information for development/troubleshooting. Disabled in production. | Variable values, query parameters, function entry/exit |
| **INFO** | Normal operational events that confirm the system is working as expected. | Request received, document processed, embedding generated, Lambda invoked |
| **WARNING** | Unexpected situations that are handled but may indicate a problem. | Missing optional config, deprecated API usage, slow response times |
| **ERROR** | Failures that prevent a specific operation from completing. The system continues running. | Database connection failure, API call error, invalid document format, missing required config |

**Note:** `CRITICAL`/`FATAL` are not used in this project. Unrecoverable failures should log at `ERROR` level and let the process exit or the Lambda invocation fail.

### Structured Logging Format (Target)

All log entries should use JSON format with the following required fields:

```json
{
  "timestamp": "2026-02-18T12:00:00.000Z",
  "level": "INFO",
  "logger": "library.stalker_web_document_db",
  "message": "Document saved successfully",
  "request_id": "abc-123-def",
  "user_id": "key_****abcd",
  "action": "document_save",
  "extra": {}
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `timestamp` | Yes | ISO 8601 UTC timestamp |
| `level` | Yes | Log level (DEBUG, INFO, WARNING, ERROR) |
| `logger` | Yes | Python module/logger name |
| `message` | Yes | Human-readable description |
| `request_id` | Yes (API) | Unique request identifier for correlation. For Lambda: use AWS request ID. For Flask: generate UUID per request. |
| `user_id` | Yes (API) | Caller identity. This project uses API keys (no user accounts), so `user_id` maps to a masked `x-api-key` value (e.g., `key_****abcd`). Never log the full key. |
| `action` | Recommended | Categorized action name (e.g., `document_save`, `embedding_generate`, `api_call`) |
| `extra` | Optional | Additional context (document_id, model_name, duration_ms, etc.) |

### Current Reality vs Target

| Aspect | Current State | Target State |
|--------|--------------|--------------|
| Format | Plain text (Python default) | Structured JSON |
| Request tracking | None | UUID per request (`request_id`) |
| Correlation | None | `request_id` propagated across service boundaries |
| Log levels | Inconsistent (some DEBUG in production) | Consistent per-environment configuration |
| Structured fields | None | Standard fields (timestamp, level, logger, message, request_id, action) |

---

## Per-Environment Configuration

### AWS (Lambda + API Gateway)

**Current setup:**
- **CloudWatch Logs**: All Lambda functions automatically emit logs to CloudWatch Log Groups (`/aws/lambda/{function-name}`)
- **API Gateway Logging**: Configured on `api-gw-app` stage only (INFO level, full request/response tracing)
- **X-Ray Tracing**: Enabled on `api-gw-app` stage (`TracingEnabled: true`) — traces API Gateway → Lambda invocations
- **Lambda LoggingConfig**: Infrastructure Lambdas (via `api-gw-infra.yaml`) have CloudFormation-level JSON logging configured (ApplicationLogLevel: INFO, SystemLogLevel: INFO)
- **CloudWatch Metrics**: API Gateway metrics enabled on app stage (request count, latency, errors)
- **CloudWatch Alarms**: None configured

**Gaps:**
- `api-gw-infra` and `api-gw-url-add` stages lack stage-level logging and tracing
- 7 infrastructure Lambdas (rds-*, ec2-*, sqs-size) use `print()` instead of Python logging module
- No CloudWatch alarms for error rate thresholds or latency spikes
- No centralized log aggregation or cross-Lambda correlation

**Recommended improvements (future stories):**
1. Add StageDescription with logging/tracing to `api-gw-infra` and `api-gw-url-add` templates
2. Replace `print()` with Python `logging` module in infrastructure Lambdas
3. Enable X-Ray SDK instrumentation in application Lambda code
4. Configure CloudWatch alarms for 5xx error rates and P99 latency

### Docker / Local Development

**Current setup:**
- **Logging**: Python `logging` module outputs to stdout/stderr, captured by Docker container logs (`docker logs lenie-ai-server`)
- **Tracing**: None
- **Metrics**: `/metrics` endpoint exists but its implementation is `pass` (returns `None`), which causes Flask to raise a `TypeError` / 500 error (`server.py:695-697`)
- **Health checks**: Docker Compose does not configure health checks. Flask exposes `/healthz` (`server.py:689-691`) which returns `{"status": "OK"}`, but it is not used by Docker Compose. Kubernetes-specific probes (`/startup`, `/readiness`, `/liveness`) also exist but are unused in Docker.

**Gaps:**
- No structured logging (JSON) — plain text output
- No request ID tracking
- `/metrics` endpoint is a stub with no implementation
- No Docker Compose health check configuration

**Recommended improvements (future stories):**
1. Add `python-json-logger` or equivalent for structured JSON output
2. Generate and propagate request IDs via Flask middleware
3. Add Docker Compose healthcheck using `/healthz` endpoint

### Kubernetes

**Current setup:**
- **Logging**: Python `logging` module outputs to stdout/stderr — Kubernetes captures container stdout as pod logs
- **Tracing**: None
- **Metrics**: `/metrics` endpoint exists (stub, currently returns 500) — could be consumed by Prometheus if implemented
- **Health probes**: Fully configured (startupProbe, readinessProbe, livenessProbe) in both Helm and Kustomize deployments
- **Pod logs**: Accessible via `kubectl logs <pod-name>`

**Gaps:**
- No log aggregation (future: stdout → Fluentd/Fluent Bit → centralized storage)
- No Prometheus metrics implementation (stub endpoint only)
- No distributed tracing (future: OpenTelemetry or Jaeger)

**Recommended improvements (future stories):**
1. Implement Prometheus metrics via `prometheus_client` library
2. Deploy Fluent Bit DaemonSet for log aggregation
3. Add OpenTelemetry instrumentation for distributed tracing

### GCloud (Future)

**Planned setup:**
- **Logging**: Cloud Logging (automatic for GKE pods writing to stdout)
- **Tracing**: Cloud Trace
- **Metrics**: Cloud Monitoring
- **Integration**: Cloud Logging agent auto-collects stdout/stderr from GKE containers

No GCloud deployment exists yet — this section will be updated when GCloud support is implemented.

---

## Tools Inventory

### Installed but Unused Tools

| Tool | Location | Status | Decision |
|------|----------|--------|----------|
| **aws-xray-sdk** | `pyproject.toml:63` (docker extra), `pyproject.toml:82` (all extra) | Dependency installed in Docker and all extras. **NOT imported or used** in any application code. | **Keep for now** — needed when X-Ray instrumentation is implemented in Lambda application code. Remove if X-Ray approach is abandoned. |
| **Langfuse** | `pyproject.toml:32` (base dependency), `library/api/openai/openai_my.py:5` (commented import: `# from langfuse.decorators import observe`) | Dependency installed. Import and `@observe()` decorator commented out (line 5, 14). | **Keep for now** — useful for LLM call tracing and cost tracking. Activate when LLM observability becomes a priority. |
| **Prometheus `/metrics`** | `server.py:695-697` | Endpoint exists but implementation is `pass` (returns `None`, causing Flask 500 error). `prometheus_client` library is **NOT installed**. | **Keep stub** — implement with `prometheus_client` when Kubernetes monitoring is set up. The route registration ensures the path is reserved for future use. |

### Removed Tools

| Tool | Removed In | Reason |
|------|-----------|--------|
| **AWS RUM (Real User Monitoring)** | Story 5-2 | Frontend monitoring code was dead/unused. Completely removed — no residual references. |

### Active Tools

| Tool | Location | Status |
|------|----------|--------|
| **Python `logging` module** | All backend files | Active — standard library, no dependency needed |
| **CloudWatch Logs** | AWS Lambda functions | Active — automatic for all Lambda functions |
| **CloudWatch Metrics** | API Gateway app stage | Active — via StageDescription MetricsEnabled |
| **X-Ray (API Gateway level)** | `api-gw-app.yaml:589` | Active — TracingEnabled at API Gateway stage level (not SDK-level in application code) |
| **Lambda LoggingConfig** | `api-gw-infra.yaml` | Active — JSON format, INFO level for infrastructure Lambda functions |
| **Kubernetes health probes** | Helm + Kustomize configs | Active — startup, readiness, liveness probes configured |

---

## Request Audit Trail

### Current State

There is **no centralized request audit trail**. API Gateway access logs are available in CloudWatch (for the app stage) but there is no application-level audit logging.

### Target Strategy

Every API request should be logged with the following information for audit and debugging purposes:

| Field | Source | Purpose |
|-------|--------|---------|
| `timestamp` | Generated at request start | When the request occurred |
| `request_id` | Generated UUID (Flask) or AWS Request ID (Lambda) | Unique identifier for request correlation |
| `method` | `request.method` | HTTP method (GET, POST, PUT, DELETE) |
| `path` | `request.path` | API endpoint path |
| `status_code` | Response status | HTTP response status |
| `response_time_ms` | Calculated | Request processing duration |
| `api_key_identity` | `x-api-key` header (hashed or masked) | Caller identification (never log the full key) |
| `content_type` | `request.content_type` | Request content type |
| `user_agent` | `request.headers['User-Agent']` | Client identification |

### Implementation Approach (Future Story)

**Flask (Docker/Kubernetes):**
- Add `@app.before_request` middleware to generate `request_id` and record start time
- Add `@app.after_request` middleware to log the audit entry with response status and duration
- Store `request_id` in Flask's `g` object for propagation to downstream loggers

**Lambda (AWS):**
- Use the AWS Lambda request context ID (`context.aws_request_id`) as the `request_id`
- Log audit entry at the start and end of each Lambda handler invocation
- API Gateway access logging provides additional audit data in CloudWatch

**Example audit log entry (target format):**

```json
{
  "timestamp": "2026-02-18T12:00:00.000Z",
  "level": "INFO",
  "action": "request_audit",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "POST",
  "path": "/website_save",
  "status_code": 200,
  "response_time_ms": 142,
  "api_key_identity": "key_****abcd",
  "content_type": "application/json",
  "user_agent": "Mozilla/5.0"
}
```

### Security Considerations

- **Never log** full API keys, passwords, or sensitive request/response bodies
- **Mask or hash** `x-api-key` values in audit logs (e.g., show only last 4 characters)
- **Review** `DataTraceEnabled: true` on API Gateway app stage — this logs full request/response bodies to CloudWatch, which may include sensitive data
- **Retention**: Define CloudWatch log retention policies to manage storage costs and comply with data handling requirements
