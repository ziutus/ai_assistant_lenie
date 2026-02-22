# Story 18.2: Analyze RDS Lambda Consolidation

Status: ready-for-dev

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

- [ ] Task 1: Analyze current RDS Lambda functions (AC: #1, #2)
  - [ ] Review source code: `lambdas/rds-start/`, `lambdas/rds-stop/`, `lambdas/rds-status/`
  - [ ] Compare function configurations (memory, timeout, runtime, env vars, layers)
  - [ ] Check IAM permissions scope (rds:StartDBInstance, rds:StopDBInstance, rds:DescribeDBInstances)
  - [ ] Map invocation sources: API Gateway AND Step Functions
  - [ ] Measure code overlap and shared logic
- [ ] Task 2: Analyze Step Function integration (AC: #3)
  - [ ] Review `sqs-to-rds-step-function.yaml` — which RDS functions does it invoke?
  - [ ] Determine if Step Function uses function name or ARN
  - [ ] Evaluate impact of changing function name/routing on Step Function ASL
  - [ ] Check if Step Function passes parameters that could serve as action routing
- [ ] Task 3: Evaluate consolidation and write joint recommendation (AC: #1, #4)
  - [ ] Consider 4 options: (a) keep all separate, (b) consolidate EC2 only, (c) consolidate RDS only, (d) single "infra-management" Lambda for all 6+1 functions
  - [ ] For each option: effort estimate, maintenance savings, risk assessment
  - [ ] Document findings in this story file (Dev Agent Record section)
  - [ ] Provide clear recommendation with rationale

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
- **rds-start and rds-status also invoked by `sqs-to-rds-step-function.yaml`** — this is a critical dependency

### Step Function Dependency (CRITICAL)

The `sqs-to-rds-step-function.yaml` orchestrates:
1. Check RDS status (`rds-status`)
2. If stopped → start RDS (`rds-start`)
3. Wait for RDS to be available
4. Process SQS messages (`sqs-to-rds-lambda`)
5. Stop RDS (`rds-stop`)

If RDS Lambdas are consolidated, the Step Function ASL definition must be updated to:
- Pass an `action` parameter to the consolidated function
- Or use different input payloads for each step

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

### Debug Log References

### Completion Notes List

### File List
