# Story 18.2: Analyze RDS Lambda Consolidation

Status: done

## Story

As a **developer**,
I want to analyze whether the RDS management Lambda functions (rds-start, rds-stop, rds-status) can be consolidated into a single function,
so that I can reduce infrastructure complexity and maintenance overhead.

## Acceptance Criteria

1. **Given** three separate Lambda functions exist for RDS management
   **When** the developer analyzes their code, configuration, and usage
   **Then** a written analysis document is produced with a clear recommendation (consolidate or keep separate)

2. **Given** the analysis is complete
   **When** the developer reviews the findings
   **Then** the document includes: current resource costs, code overlap, shared dependencies, Step Function integration impact, and migration complexity

3. **Given** the RDS functions are used by `sqs-to-rds-step-function.yaml`
   **When** the developer evaluates consolidation
   **Then** the analysis explicitly addresses Step Function integration — how the consolidated function would be invoked and whether ASL definition changes are needed

4. **Given** Story 18.1 (EC2 analysis) may recommend consolidation
   **When** the developer completes the RDS analysis
   **Then** a joint recommendation is provided: consolidate EC2 only, RDS only, both into one function, or keep all separate

## Tasks / Subtasks

- [x] Task 1: Analyze current RDS Lambda functions (AC: #1, #2)
  - [x] Review source code: `lambdas/rds-start/`, `lambdas/rds-stop/`, `lambdas/rds-status/`
  - [x] Compare function configurations (memory, timeout, runtime, env vars, layers)
  - [x] Check IAM permissions scope (rds:StartDBInstance, rds:StopDBInstance, rds:DescribeDBInstances)
  - [x] Map invocation sources: API Gateway AND Step Functions
  - [x] Measure code overlap and shared logic
- [x] Task 2: Analyze Step Function integration (AC: #3)
  - [x] Review `sqs-to-rds-step-function.yaml` — which RDS functions does it invoke?
  - [x] Determine if Step Function uses function name or ARN
  - [x] Evaluate impact of changing function name/routing on Step Function ASL
  - [x] Check if Step Function passes parameters that could serve as action routing
- [x] Task 3: Evaluate consolidation and write joint recommendation (AC: #1, #4)
  - [x] Consider 4 options: (a) keep all separate, (b) consolidate EC2 only, (c) consolidate RDS only, (d) single "infra-management" Lambda for all 6+1 functions
  - [x] For each option: effort estimate, maintenance savings, risk assessment
  - [x] Document findings in this story file (Dev Agent Record section)
  - [x] Provide clear recommendation with rationale

## Dev Notes

### Current RDS Lambda Architecture

Three Lambda functions defined in `api-gw-infra.yaml`:
- `${ProjectCode}-${Environment}-rds-start` (line 98) — starts RDS instance
- `${ProjectCode}-${Environment}-rds-stop` (line 124) — stops RDS instance
- `${ProjectCode}-${Environment}-rds-status` (line 150) — checks RDS instance status

All three:
- Defined inline in `api-gw-infra.yaml`
- Share the same IAM execution role (`InfraLambdaExecutionRole`)
- Have similar configuration
- Exposed via `api-gw-infra` REST API endpoints
- Exposed via `api-gw-infra` REST API endpoints

### Step Function Dependency — CORRECTED

**Original assumption was WRONG.** After analyzing the actual Step Function ASL definition:

The `sqs-to-rds-step-function.yaml` uses **direct AWS SDK integrations**, NOT Lambda invocations for RDS operations:
- `rds:describeDBInstances` — direct SDK call (not rds-status Lambda)
- `rds:startDBInstance` — direct SDK call (not rds-start Lambda)
- `rds:stopDBInstance` — direct SDK call (not rds-stop Lambda)

The only Lambda invoked by the Step Function is `sqs-to-rds-lambda` (for processing SQS messages).

**Conclusion: Step Function has ZERO dependency on RDS Lambda functions.** Consolidating or renaming RDS Lambdas has NO impact on the Step Function.

### Additional Function: sqs-size

The `api-gw-infra.yaml` also defines `sqs-size` Lambda — consider whether it belongs in the consolidation scope (total: 7 infrastructure Lambdas).

### Historical Note: lambda-rds-start.yaml

There was a separate `lambda-rds-start.yaml` template (now commented out in deploy.ini, line 36). The rds-start Lambda is now managed within `api-gw-infra.yaml`. The old stack `lenie-dev-lambda-rds-start` should be deleted manually if it still exists.

### Analysis Framework

Same as Story 18.1, plus:
1. **Step Function coupling** — how tightly are RDS functions integrated?
2. **Invocation payload** — does the Step Function pass structured events?
3. **Error handling** — does consolidation affect Step Function retry logic?
4. **Deployment risk** — changing function names breaks Step Function until ASL is updated

### Key Constraints

- This is an **analysis story** — no code changes, only a recommendation document
- **Must coordinate with Story 18.1** — produce a joint recommendation
- Step Function integration is the biggest differentiator vs. EC2 analysis
- Consider that `api-gw-infra.yaml` already defines all 7 infra functions in one template

### References

- [Source: infra/aws/cloudformation/templates/api-gw-infra.yaml:98-160 — RDS Lambda definitions]
- [Source: infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml — Step Function using RDS Lambdas]
- [Source: infra/aws/serverless/lambdas/rds-start/ — source code]
- [Source: infra/aws/serverless/lambdas/rds-stop/ — source code]
- [Source: infra/aws/serverless/lambdas/rds-status/ — source code]
- [Source: infra/aws/serverless/CLAUDE.md — function inventory]
- [Source: Story 18.1 — EC2 consolidation analysis (coordinate)]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Analysis Results

#### 1. Current State — Source Code Analysis

| Function | File | Lines | Size | AWS API Call | Env Var |
|----------|------|-------|------|-------------|---------|
| rds-start | `lambdas/rds-start/lambda_function.py` | 30 | 892 B | `rds.start_db_instance()` | DB_ID |
| rds-stop | `lambdas/rds-stop/lambda_function.py` | 30 | 891 B | `rds.stop_db_instance()` | DB_ID |
| rds-status | `lambdas/rds-status/lambda_function.py` | 44 | 1,406 B | `rds.describe_db_instances()` | DB_ID |

**All functions share identical structure:**
- Imports: `boto3`, `os`, `json` (rds-status also imports `pprint`)
- Handler: `lambda_handler(event, context)`
- Pattern: get env var → try AWS call → return CORS response → catch exception
- boto3 client created at **module level** (more efficient than EC2 pattern)

#### 2. Current State — CloudFormation Configuration

All three defined in `api-gw-infra.yaml`:

| Setting | rds-start | rds-stop | rds-status |
|---------|-----------|----------|------------|
| Memory | 128 MB | 128 MB | 128 MB |
| Timeout | **60s** | 30s | 30s |
| Runtime | SSM-resolved (python3.11) | Same | Same |
| IAM Role | InfraLambdaExecutionRole (shared) | Same | Same |
| Env Vars | LOG_LEVEL, DB_ID | Same | Same |
| VPC | None | None | None |
| Layers | None | None | None |

**Note:** rds-start has 60s timeout (vs 30s for others) — RDS start can take longer.

**API Gateway Endpoints:**
- `POST /database/start` → rds-start
- `POST /database/stop` → rds-stop
- `GET /database/status` → rds-status
- All require `x-api-key` header

#### 3. Code Overlap Analysis

**Shared boilerplate:** ~20 lines per function (67-70%)
- Import block (3 lines)
- Module-level client + env var (2 lines)
- CORS response template for success (6 lines)
- Exception handler with error response (6 lines)
- Handler signature (1 line)

**Unique code per function:** ~10 lines (30%)
- The AWS API call
- Response message strings
- For status: response parsing + instance count validation

**Cross-function similarity:**
- rds-start vs rds-stop: **98%** (1 API call + message strings differ)
- rds-start vs rds-status: **85%** (API call + response parsing + extra validation)
- rds-stop vs rds-status: **85%**

#### 4. Step Function Integration Analysis (AC #3)

**CRITICAL FINDING:** The Step Function does **NOT** invoke RDS Lambda functions.

After analyzing `sqs-to-rds-step-function.yaml` ASL definition, the Step Function uses:
- **`rds:describeDBInstances`** — direct AWS SDK integration (Type: Task, Resource: `arn:aws:states:::aws-sdk:rds:describeDBInstances`)
- **`rds:startDBInstance`** — direct AWS SDK integration
- **`rds:stopDBInstance`** — direct AWS SDK integration

The Step Function has its **own IAM role** (`StateMachineRole`) with direct RDS permissions:
- `rds:DescribeDBInstances`
- `rds:StartDBInstance`
- `rds:StopDBInstance`

The only Lambda invoked by the Step Function is `sqs-to-rds-lambda` (via `arn:aws:states:::lambda:invoke`).

**Impact of Lambda consolidation on Step Function: ZERO.** No ASL changes needed. No function name dependencies.

#### 5. IAM Permissions Analysis

Current `InfraLambdaExecutionRole` already grants all 3 RDS permissions:
- `rds:StartDBInstance` (all RDS databases in account)
- `rds:StopDBInstance` (all RDS databases in account)
- `rds:DescribeDBInstances` (all RDS databases in account)

**Conclusion:** A consolidated function would use the SAME IAM role — no permission escalation.

#### 6. Bugs Found in RDS Lambda Code

| Bug | Function | Severity | Description |
|-----|----------|----------|-------------|
| Wrong error message | rds-start | Medium | Error message says "Error during **stopping** database" (should say "starting") |
| Wrong success message | rds-stop | Medium | Success message says "The database has been **started**" (should say "stopped") |
| Non-JSON body | rds-status | Low | Returns raw string in body (not JSON) for success — inconsistent with other functions |
| Bare pass | rds-status | Low | Contains `pass` statement before exception handler (antipattern) |
| Missing env var validation | All 3 | Low | Unlike EC2 functions, RDS functions don't validate if DB_ID is set |
| Inconsistent CORS | rds-start, rds-stop | Low | Error responses have `Access-Control-Allow-Methods` header but success responses don't |

**These bugs should be fixed during consolidation.**

#### 7. sqs-size Lambda Analysis

| Setting | Value |
|---------|-------|
| File | `lambdas/sqs-size/lambda_function.py` |
| Lines | 44 |
| AWS APIs | `ssm.get_parameter()`, `sqs.get_queue_attributes()` |
| Env Vars | AWS_REGION |
| Purpose | Get SQS queue message count |

**Consolidation scope:** sqs-size is functionally different (SQS + SSM, not resource start/stop/status). It uses different AWS services, different env vars, and serves a different purpose.

**Recommendation: Keep sqs-size SEPARATE.** It doesn't fit the start/stop/status pattern.

### Joint Recommendation (AC #4) — All 4 Options Evaluated

#### Option A: Keep All Separate

| Dimension | Assessment |
|-----------|-----------|
| Effort | 0 (no work) |
| Maintenance | HIGH — 6 nearly identical files, 6 CF Lambda definitions |
| Risk | 0 |
| Code debt | 6 buggy functions, ~70% duplication |

**Verdict: NOT RECOMMENDED** — perpetuates code duplication and known bugs.

#### Option B: Consolidate EC2 Only (3 → 1)

| Dimension | Assessment |
|-----------|-----------|
| Effort | LOW (~2h) |
| Maintenance savings | Moderate — 3→1 Lambda, 2 fewer CF resources |
| Risk | LOW — API endpoints unchanged |
| Net benefit | Positive but incomplete |

**Verdict: ACCEPTABLE but leaves RDS bugs unfixed.**

#### Option C: Consolidate RDS Only (3 → 1)

| Dimension | Assessment |
|-----------|-----------|
| Effort | LOW (~2h) |
| Maintenance savings | Moderate — 3→1 Lambda, 2 fewer CF resources |
| Risk | LOW — Step Function NOT dependent on these Lambdas |
| Net benefit | Positive, fixes RDS bugs |

**Verdict: ACCEPTABLE but leaves EC2 duplication.**

#### Option D: Two Consolidated Functions — ec2-manager + rds-manager (6 → 2)

| Dimension | Assessment |
|-----------|-----------|
| Effort | LOW-MEDIUM (~3-4h) |
| Maintenance savings | HIGH — 6→2 Lambdas, 4 fewer CF resources, 4 fewer Permission resources |
| Risk | LOW — No Step Function dependency, API endpoints unchanged |
| Code reduction | ~60% across both function groups |
| Bug fixes | All 6 known bugs resolved during consolidation |
| Clean boundaries | EC2 and RDS remain separate services with separate env vars |

**Verdict: RECOMMENDED**

#### Option E: Single infra-manager for all 6+1 (7 → 1)

| Dimension | Assessment |
|-----------|-----------|
| Effort | MEDIUM (~5-6h) |
| Maintenance savings | HIGHEST — 7→1 Lambda |
| Risk | MEDIUM — larger blast radius, mixed env vars (INSTANCE_ID + DB_ID + SSM), sqs-size doesn't fit pattern |
| Complexity | Routing logic more complex (resource_type + action), harder to debug |
| Monitoring | All operations mixed in one CloudWatch log group |

**Verdict: OVER-ENGINEERING.** The additional complexity of mixing EC2, RDS, and SQS in one function outweighs marginal maintenance savings over Option D.

### Final Recommendation

**Option D: Two consolidated functions (ec2-manager + rds-manager)**

Rationale:
1. **Best effort-to-benefit ratio** — 3-4 hours of work for 60% code reduction
2. **Clean service boundaries** — EC2 and RDS are logically separate; each manager has exactly the env vars it needs
3. **No external dependencies** — Step Function uses direct SDK calls, not Lambda
4. **Bug fixes included** — all 6 known bugs resolved during consolidation
5. **Low risk** — API endpoints unchanged, IAM role unchanged
6. **Keep sqs-size separate** — it's a different pattern (read-only SQS query, not infrastructure lifecycle management)

### Implementation Steps (Future Stories)

**Story A: Create ec2-manager Lambda (from 18-1)**
1. Create `lambdas/ec2-manager/lambda_function.py` with action routing
2. Update `api-gw-infra.yaml`: remove 3 EC2 Lambdas, add 1 Ec2ManagerFunction
3. Update API Gateway integrations
4. Remove old directories, update function_list_cf.txt
5. Estimated: 2h

**Story B: Create rds-manager Lambda**
1. Create `lambdas/rds-manager/lambda_function.py` with action routing
2. Fix bugs: correct error/success messages, add JSON response, add env var validation
3. Update `api-gw-infra.yaml`: remove 3 RDS Lambdas, add 1 RdsManagerFunction
4. Update API Gateway integrations
5. rds-manager gets 60s timeout (from rds-start, higher than others)
6. Remove old directories, update function_list_cf.txt
7. Estimated: 2h

**Both stories can be implemented in parallel.**

### Debug Log References

- RDS source code analysis: `infra/aws/serverless/lambdas/rds-{start,stop,status}/lambda_function.py`
- sqs-size source code: `infra/aws/serverless/lambdas/sqs-size/lambda_function.py`
- CloudFormation analysis: `infra/aws/cloudformation/templates/api-gw-infra.yaml` (lines 68-171 for RDS/SQS Lambdas)
- Step Function ASL analysis: `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml` (lines 113-378)
- Step Function uses `arn:aws:states:::aws-sdk:rds:*` (direct SDK), NOT `arn:aws:states:::lambda:invoke` for RDS operations
- Story 18-1 EC2 analysis: `_bmad-output/implementation-artifacts/18-1-analyze-ec2-lambda-consolidation.md`

### Completion Notes List

- Analysis complete: Joint recommendation = Option D (ec2-manager + rds-manager)
- CRITICAL CORRECTION: Step Function has ZERO dependency on RDS Lambda functions (uses direct AWS SDK)
- 6 bugs identified in RDS Lambda code (copy-paste errors in messages)
- sqs-size excluded from consolidation scope (different pattern)
- No code changes made (analysis-only story)

### File List

Files analyzed (read-only):
- `infra/aws/serverless/lambdas/rds-start/lambda_function.py`
- `infra/aws/serverless/lambdas/rds-stop/lambda_function.py`
- `infra/aws/serverless/lambdas/rds-status/lambda_function.py`
- `infra/aws/serverless/lambdas/sqs-size/lambda_function.py`
- `infra/aws/cloudformation/templates/api-gw-infra.yaml`
- `infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml`
- `_bmad-output/implementation-artifacts/18-1-analyze-ec2-lambda-consolidation.md`
