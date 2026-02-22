# Story 18.1: Analyze EC2 Lambda Consolidation

Status: ready-for-dev

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

- [ ] Task 1: Analyze current EC2 Lambda functions (AC: #1, #2)
  - [ ] Review source code: `lambdas/ec2-start/`, `lambdas/ec2-stop/`, `lambdas/ec2-status/`
  - [ ] Compare function configurations (memory, timeout, runtime, env vars, layers)
  - [ ] Check IAM permissions — can they share a role?
  - [ ] Check invocation patterns (API Gateway only? Step Functions? EventBridge?)
  - [ ] Measure code overlap and shared logic
- [ ] Task 2: Evaluate consolidation feasibility (AC: #3, #4)
  - [ ] Design single-function routing (path-based or parameter-based)
  - [ ] Assess API Gateway changes needed (api-gw-infra.yaml)
  - [ ] Evaluate cold start impact (larger function = longer cold start?)
  - [ ] Consider IAM least-privilege implications
  - [ ] Estimate migration effort vs. maintenance savings
- [ ] Task 3: Write analysis document (AC: #1, #2, #3 or #4)
  - [ ] Document findings in this story file (Dev Agent Record section)
  - [ ] Provide clear recommendation with rationale
  - [ ] If consolidating: outline implementation steps for a future story

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

### Debug Log References

### Completion Notes List

### File List
