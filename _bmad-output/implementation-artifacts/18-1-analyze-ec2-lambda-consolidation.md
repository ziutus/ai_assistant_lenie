# Story 18.1: Analyze EC2 Lambda Consolidation

Status: done

## Story

As a **developer**,
I want to analyze whether the EC2 management Lambda functions (ec2-start, ec2-stop, ec2-status) can be consolidated into a single function,
so that I can reduce infrastructure complexity and maintenance overhead.

## Acceptance Criteria

1. **Given** three separate Lambda functions exist for EC2 management
   **When** the developer analyzes their code, configuration, and usage
   **Then** a written analysis document is produced with a clear recommendation (consolidate or keep separate)

2. **Given** the analysis is complete
   **When** the developer reviews the findings
   **Then** the document includes: current resource costs (memory, timeout, invocation patterns), code overlap percentage, shared dependencies, and migration complexity

3. **Given** a consolidation recommendation
   **When** the developer proposes the new architecture
   **Then** the proposal includes: single function with action parameter routing, updated API Gateway integration, backward compatibility plan

4. **Given** a keep-separate recommendation
   **When** the developer documents the rationale
   **Then** the document explains why consolidation is not beneficial (e.g., different VPC requirements, IAM scoping, cold start impact)

## Tasks / Subtasks

- [x] Task 1: Analyze current EC2 Lambda functions (AC: #1, #2)
  - [x] Review source code: `lambdas/ec2-start/`, `lambdas/ec2-stop/`, `lambdas/ec2-status/`
  - [x] Compare function configurations (memory, timeout, runtime, env vars, layers)
  - [x] Check IAM permissions — can they share a role?
  - [x] Check invocation patterns (API Gateway only? Step Functions? EventBridge?)
  - [x] Measure code overlap and shared logic
- [x] Task 2: Evaluate consolidation feasibility (AC: #3, #4)
  - [x] Design single-function routing (path-based or parameter-based)
  - [x] Assess API Gateway changes needed (api-gw-infra.yaml)
  - [x] Evaluate cold start impact (larger function = longer cold start?)
  - [x] Consider IAM least-privilege implications
  - [x] Estimate migration effort vs. maintenance savings
- [x] Task 3: Write analysis document (AC: #1, #2, #3 or #4)
  - [x] Document findings in this story file (Dev Agent Record section)
  - [x] Provide clear recommendation with rationale
  - [x] If consolidating: outline implementation steps for a future story

## Dev Notes

### Current EC2 Lambda Architecture

Three Lambda functions defined in `api-gw-infra.yaml`:
- `${ProjectCode}-${Environment}-ec2-start` (line 202) — starts EC2 instance
- `${ProjectCode}-${Environment}-ec2-stop` (line 228) — stops EC2 instance
- `${ProjectCode}-${Environment}-ec2-status` (line 176) — checks EC2 instance state

All three:
- Defined inline in `api-gw-infra.yaml` (not separate templates)
- Share the same IAM execution role (`InfraLambdaExecutionRole`)
- Have similar configuration (python3.11, simple functions)
- Exposed via `api-gw-infra` REST API endpoints

### Related: RDS Lambdas (Story 18.2)

The same analysis applies to RDS functions (rds-start, rds-stop, rds-status). Consider whether EC2 and RDS functions could ALL be consolidated into a single "infrastructure management" Lambda. Story 18.2 analyzes this for RDS specifically.

### Analysis Framework

Evaluate these dimensions:
1. **Code similarity** — how much shared vs. unique code?
2. **Configuration parity** — same runtime, memory, timeout, VPC?
3. **IAM scope** — can a single role serve all actions without over-permissioning?
4. **Invocation patterns** — all via API GW, or also Step Functions/EventBridge?
5. **Cold start budget** — is combined package size acceptable?
6. **Maintenance cost** — fewer functions = less CF template maintenance
7. **Monitoring** — separate functions have clearer CloudWatch metrics per action

### Key Constraints

- This is an **analysis story** — no code changes, only a recommendation document
- The output feeds into a potential future implementation story
- Consider the interaction with Story 18.2 (RDS consolidation) — a joint recommendation may be appropriate

### References

- [Source: infra/aws/cloudformation/templates/api-gw-infra.yaml:176-237 — EC2 Lambda definitions]
- [Source: infra/aws/serverless/lambdas/ec2-start/ — source code]
- [Source: infra/aws/serverless/lambdas/ec2-stop/ — source code]
- [Source: infra/aws/serverless/lambdas/ec2-status/ — source code]
- [Source: infra/aws/serverless/CLAUDE.md — function inventory]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Analysis Results

#### 1. Current State — Source Code Analysis

| Function | File | Lines | Size | AWS API Call | Env Var |
|----------|------|-------|------|-------------|---------|
| ec2-start | `lambdas/ec2-start/lambda_function.py` | 40 | 1,301 B | `ec2.start_instances()` | INSTANCE_ID |
| ec2-stop | `lambdas/ec2-stop/lambda_function.py` | 40 | 1,300 B | `ec2.stop_instances()` | INSTANCE_ID |
| ec2-status | `lambdas/ec2-status/lambda_function.py` | 41 | 1,367 B | `ec2.describe_instances()` | INSTANCE_ID |

**All functions share identical structure:**
- Imports: `boto3`, `os`, `json`
- Handler: `lambda_handler(event, context)`
- Pattern: validate env var → try AWS call → return CORS response → catch exception
- boto3 client created inside handler (per invocation, not module-level)

#### 2. Current State — CloudFormation Configuration

All three defined in `api-gw-infra.yaml`:

| Setting | ec2-start | ec2-stop | ec2-status |
|---------|-----------|----------|------------|
| Memory | 128 MB | 128 MB | 128 MB |
| Timeout | 30s | 30s | 30s |
| Runtime | SSM-resolved (python3.11) | Same | Same |
| IAM Role | InfraLambdaExecutionRole (shared) | Same | Same |
| Env Vars | LOG_LEVEL, INSTANCE_ID | Same | Same |
| VPC | None | None | None |
| Layers | None | None | None |

**API Gateway Endpoints (api-gw-infra.yaml):**
- `POST /vpn_server/start` → ec2-start
- `POST /vpn_server/stop` → ec2-stop
- `GET /vpn_server/status` → ec2-status
- All require `x-api-key` header
- Integration timeout: 29s

#### 3. Code Overlap Analysis

**Shared boilerplate:** ~28 lines per function (69% of code)
- Import block (3 lines)
- Handler signature + client init + env var read (3 lines)
- INSTANCE_ID validation with 400 response (8 lines)
- CORS response template for success (7 lines)
- Exception handler with 500 response (7 lines)

**Unique code per function:** ~12 lines (31%)
- The single AWS API call
- Response message strings
- For status: response parsing (`response['Reservations'][0]['Instances'][0]['State']['Name']`)

**Cross-function similarity:**
- ec2-start vs ec2-stop: **99%** (differ in 1 API call + message strings)
- ec2-start vs ec2-status: **93%** (differ in API call + response parsing)
- ec2-stop vs ec2-status: **93%**

#### 4. IAM Permissions Analysis

Current `InfraLambdaExecutionRole` already grants all 3 EC2 permissions:
- `ec2:StartInstances` (all resources)
- `ec2:StopInstances` (all resources)
- `ec2:DescribeInstances` (all resources)

**Conclusion:** A consolidated function would use the SAME IAM role — no permission escalation.

#### 5. Invocation Patterns

- **API Gateway only** — all 3 functions are invoked exclusively via REST API
- **NOT used by Step Functions** — sqs-to-rds-step-function.yaml uses direct AWS SDK integrations for RDS, not Lambda
- **NOT used by EventBridge** — no direct EventBridge rules target these functions

#### 6. Cold Start Impact

Current: 3 separate functions × ~1 KB code = ~3 KB total
Consolidated: 1 function × ~2 KB code = ~2 KB total

**Impact: NEGLIGIBLE.** All functions use only boto3 (built into Lambda runtime). No additional dependencies. Cold start difference between 1 KB and 2 KB of pure Python is sub-millisecond.

#### 7. Monitoring Considerations

**Current:** Separate CloudWatch metrics per function (invocations, errors, duration)
**Consolidated:** Single function metrics — action differentiation via:
- Custom CloudWatch dimensions (action=start/stop/status)
- Structured logging with action field (already have JSON logging configured)

**Conclusion:** No significant monitoring regression with proper structured logging.

### Recommendation

**CONSOLIDATE** — Create a single `ec2-manager` Lambda function.

**Rationale:**
1. **69% code duplication** across 3 nearly identical functions
2. **Same IAM role** — no privilege escalation risk
3. **Same configuration** — memory, timeout, runtime, env vars all identical
4. **API Gateway only** — no Step Function or EventBridge dependencies
5. **Negligible cold start impact** — pure Python, no extra dependencies
6. **Reduced CF template complexity** — 3 Lambda + 3 Permission resources → 1 Lambda + 1 Permission

### Proposed Architecture

**Consolidated function:** `${ProjectCode}-${Environment}-ec2-manager`

**Routing approach:** Path-based via API Gateway

| Current Endpoint | New Endpoint | Action |
|-----------------|-------------|--------|
| `POST /vpn_server/start` | `POST /vpn_server/start` | start |
| `POST /vpn_server/stop` | `POST /vpn_server/stop` | stop |
| `GET /vpn_server/status` | `GET /vpn_server/status` | status |

API Gateway passes the HTTP method + resource path. The consolidated Lambda determines the action from the API Gateway event:
```python
def lambda_handler(event, context):
    resource = event.get('resource', '')  # e.g., '/vpn_server/start'
    action = resource.split('/')[-1]      # 'start', 'stop', or 'status'
```

**Alternative:** Single endpoint with query parameter (`GET /vpn_server?action=start`), but this changes the API contract — NOT recommended for backward compatibility.

**Backward compatibility plan:**
- Keep existing API endpoints unchanged (`/vpn_server/start`, `/stop`, `/status`)
- Only change the Lambda integration targets — all 3 endpoints point to the single new Lambda
- Frontend code requires NO changes
- API key authentication unchanged

### Implementation Steps (Future Story)

1. Create `lambdas/ec2-manager/lambda_function.py` with action routing
2. Update `api-gw-infra.yaml`:
   - Remove 3 separate Lambda definitions (Ec2StatusFunction, Ec2StatusStart, Ec2StatusStop)
   - Add 1 Ec2ManagerFunction definition
   - Update 3 API Gateway integrations to point to Ec2ManagerFunction
   - Remove 2 of 3 Lambda permissions (keep 1 with wildcard)
3. Deploy and test via API Gateway
4. Remove old Lambda source directories (`ec2-start/`, `ec2-stop/`, `ec2-status/`)
5. Update `function_list_cf.txt` (remove 3 entries, add 1)
6. Update documentation (CLAUDE.md, infrastructure-metrics.md)

**Estimated effort:** 2-3 hours
**Risk:** LOW — API endpoints unchanged, IAM role unchanged, simple code merge

### Quality Issues Found

1. **Inconsistency:** EC2 functions create boto3 client inside handler (per-invocation), while RDS functions create it at module level (reused across warm invocations). The consolidated function should use module-level initialization.
2. **Missing LOG_LEVEL usage:** Environment variable LOG_LEVEL='INFO' is set in CloudFormation but never used in the Lambda code (no logging library configured).

### Debug Log References

- Analysis performed by reading source code from `infra/aws/serverless/lambdas/ec2-{start,stop,status}/lambda_function.py`
- CloudFormation analysis from `infra/aws/cloudformation/templates/api-gw-infra.yaml` (lines 173-249 for EC2 Lambdas, lines 251-667 for API Gateway)
- Step Function analysis from `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` confirmed NO dependency on EC2 Lambda functions

### Completion Notes List

- Analysis complete: CONSOLIDATE recommendation with clear rationale
- Joint recommendation with Story 18-2 to be provided in that story
- No code changes made (analysis-only story)

### File List

Files analyzed (read-only):
- `infra/aws/serverless/lambdas/ec2-start/lambda_function.py`
- `infra/aws/serverless/lambdas/ec2-stop/lambda_function.py`
- `infra/aws/serverless/lambdas/ec2-status/lambda_function.py`
- `infra/aws/cloudformation/templates/api-gw-infra.yaml`
- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml`
