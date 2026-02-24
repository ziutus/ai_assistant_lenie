---
title: 'Split Shared Lambda Execution Role into Per-Function Roles'
slug: 'b21-split-lambda-iam-roles'
created: '2026-02-24'
status: 'ready-for-dev'
stepsCompleted: [1, 2, 3, 4]
tech_stack: ['AWS CloudFormation', 'AWS IAM', 'AWS Lambda', 'AWS SSM Parameter Store']
files_to_modify: ['infra/aws/cloudformation/templates/api-gw-infra.yaml', 'docs/architecture-infra.md']
code_patterns: ['CloudFormation intrinsic functions (!GetAtt, !Sub, !Ref)', 'SSM Parameter dynamic references ({{resolve:ssm:...}})', 'IAM inline policies with scoped resources', 'AWS::SSM::Parameter::Value<String> for CF parameters']
test_patterns: ['CloudFormation validate-template', 'Manual deploy to dev environment via deploy.sh']
---

# Tech-Spec: Split Shared Lambda Execution Role into Per-Function Roles

**Created:** 2026-02-24

## Overview

### Problem Statement

The `api-gw-infra.yaml` CloudFormation template uses a single shared `LambdaExecutionRole` for 3 Lambda functions (SqsSizeFunction, RdsManagerFunction, Ec2ManagerFunction). Each function gets permissions it doesn't need (e.g., SQS function gets RDS and EC2 permissions). Additionally, EC2 permissions use `Resource: '*'` which is overly broad. This violates the Principle of Least Privilege and was flagged during Epic 14 code reviews as a growing problem.

### Solution

Create 3 individual IAM roles — one per Lambda function — each scoped to only the AWS services and specific resources that function needs. EC2 and RDS resources will be scoped via SSM Parameter references. Remove the shared role. Update documentation.

### Scope

**In Scope:**
- 3 new IAM roles in `api-gw-infra.yaml` (SqsSize, RdsManager, Ec2Manager)
- Scope EC2 and RDS permissions to specific resource ARNs via SSM Parameter
- Update `Role:` references in all 3 Lambda functions
- Remove old shared `LambdaExecutionRole`
- Update `docs/architecture-infra.md`

**Out of Scope:**
- Changes to Lambda function code/logic
- Changes to API Gateway configuration
- Other CloudFormation templates
- Application Lambda roles (app-server-db, app-server-internet, etc.)

## Context for Development

### Codebase Patterns

- CloudFormation templates use `!GetAtt RoleName.Arn` to reference IAM role ARNs from Lambda functions
- SSM Parameters follow the pattern `/${ProjectCode}/${Environment}/key`
- SSM dynamic references in templates: `{{resolve:ssm:/${ProjectCode}/${Environment}/...}}`
- CF parameter type `AWS::SSM::Parameter::Value<String>` used for `OpenvpnEC2Name` (resolves EC2 instance ID at deploy time)
- Resource scoping uses `!Sub` with `${AWS::Region}` and `${AWS::AccountId}` placeholders
- All resources tagged with `Environment` and `Project` keys
- Role is referenced via `!GetAtt LambdaExecutionRole.Arn` (lines 73, 100, 126)
- The role is entirely local to `api-gw-infra.yaml` — no cross-stack references

### Files to Reference

| File | Purpose | Lines of Interest |
| ---- | ------- | ----------------- |
| `infra/aws/cloudformation/templates/api-gw-infra.yaml` | Primary file — shared role + 3 Lambdas | L21-66 (role), L68-92 (SQS), L95-119 (RDS), L121-145 (EC2) |
| `docs/architecture-infra.md` | Architecture docs — Lambda table, api-gw-infra description | L41-56 (Lambda table), L158 (api-gw-infra row) |

### Technical Decisions

- **EC2 scoping constraint:** `ec2:DescribeInstances` does NOT support resource-level permissions — requires `Resource: '*'`. The EC2 role will have two statements: start/stop scoped to instance ARN, describe with `*`.
- **RDS scoping:** All RDS actions support resource-level permissions. Scope to `arn:aws:rds:${Region}:${Account}:db:${DbInstanceId}` using SSM dynamic reference.
- **EC2 instance ARN:** Constructed from existing CF parameter `OpenvpnEC2Name` (already resolves from SSM).
- **RDS instance ID:** Available via SSM dynamic reference `{{resolve:ssm:/${ProjectCode}/${Environment}/database/name}}`.
- **SQS scoping:** `sqs:GetQueueAttributes` supports resource-level permissions. Scope to project-environment queues: `arn:aws:sqs:${Region}:${Account}:${ProjectCode}-${Environment}-*`.
- **SSM `GetParameter`:** Scoped to project namespace `/${ProjectCode}/${Environment}/*` (common to all roles).
- **CloudWatch Logs:** Common to all roles (`Resource: '*'` — standard for Lambda).
- **Role naming:** `{ProjectCode}-{Environment}-{FunctionName}-role` convention with explicit `RoleName` property.

### Current Permission Matrix

| Permission | SqsSizeFunction | RdsManagerFunction | Ec2ManagerFunction |
|---|:---:|:---:|:---:|
| logs:CreateLogGroup/CreateLogStream/PutLogEvents | NEEDS | NEEDS | NEEDS |
| rds:StartDBInstance/StopDBInstance/DescribeDBInstances | - | NEEDS | - |
| ec2:StartInstances/StopInstances | - | - | NEEDS |
| ec2:DescribeInstances | - | - | NEEDS |
| sqs:GetQueueAttributes | NEEDS | - | - |
| ssm:GetParameter | NEEDS | NEEDS | NEEDS |

### SSM Parameters Used

| SSM Path | Used By | Purpose |
|---|---|---|
| `/${ProjectCode}/${Environment}/database/name` | RdsManagerFunction (env var `DB_ID`), SqsSizeFunction (env var `DB_ID`) | RDS instance identifier |
| `OpenvpnEC2Name` (CF parameter) | Ec2ManagerFunction (env var `INSTANCE_ID`) | EC2 instance ID |
| `/${ProjectCode}/${Environment}/s3/cloudformation/name` | All functions | S3 bucket for Lambda code |
| `/${ProjectCode}/${Environment}/python/lambda-runtime-version` | All functions | Python runtime version |

## Implementation Plan

### Tasks

- [ ] Task 1: Create `SqsSizeExecutionRole` IAM role
  - File: `infra/aws/cloudformation/templates/api-gw-infra.yaml`
  - Action: Add new `AWS::IAM::Role` resource after the existing `LambdaExecutionRole` block (after line 66). The role includes:
    - `RoleName: !Sub '${ProjectCode}-${Environment}-sqs-size-role'`
    - `AssumeRolePolicyDocument` — Lambda service trust
    - Policy `SqsSizePolicy` with 3 statements:
      1. CloudWatch Logs (`logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`) — `Resource: '*'`
      2. SQS (`sqs:GetQueueAttributes`) — `Resource: !Sub 'arn:aws:sqs:${AWS::Region}:${AWS::AccountId}:${ProjectCode}-${Environment}-*'`
      3. SSM (`ssm:GetParameter`) — `Resource: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/${ProjectCode}/${Environment}/*'`
    - Tags: `Environment` + `Project` (same pattern as existing)

- [ ] Task 2: Create `RdsManagerExecutionRole` IAM role
  - File: `infra/aws/cloudformation/templates/api-gw-infra.yaml`
  - Action: Add new `AWS::IAM::Role` resource. The role includes:
    - `RoleName: !Sub '${ProjectCode}-${Environment}-rds-manager-role'`
    - `AssumeRolePolicyDocument` — Lambda service trust
    - Policy `RdsManagerPolicy` with 3 statements:
      1. CloudWatch Logs — `Resource: '*'`
      2. RDS (`rds:StartDBInstance`, `rds:StopDBInstance`, `rds:DescribeDBInstances`) — `Resource: !Sub 'arn:aws:rds:${AWS::Region}:${AWS::AccountId}:db:{{resolve:ssm:/${ProjectCode}/${Environment}/database/name}}'`
      3. SSM (`ssm:GetParameter`) — `Resource: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/${ProjectCode}/${Environment}/*'`
    - Tags: `Environment` + `Project`

- [ ] Task 3: Create `Ec2ManagerExecutionRole` IAM role
  - File: `infra/aws/cloudformation/templates/api-gw-infra.yaml`
  - Action: Add new `AWS::IAM::Role` resource. The role includes:
    - `RoleName: !Sub '${ProjectCode}-${Environment}-ec2-manager-role'`
    - `AssumeRolePolicyDocument` — Lambda service trust
    - Policy `Ec2ManagerPolicy` with 4 statements:
      1. CloudWatch Logs — `Resource: '*'`
      2. EC2 Start/Stop (`ec2:StartInstances`, `ec2:StopInstances`) — `Resource: !Sub 'arn:aws:ec2:${AWS::Region}:${AWS::AccountId}:instance/${OpenvpnEC2Name}'`
      3. EC2 Describe (`ec2:DescribeInstances`) — `Resource: '*'` (API does not support resource-level permissions)
      4. SSM (`ssm:GetParameter`) — `Resource: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/${ProjectCode}/${Environment}/*'`
    - Tags: `Environment` + `Project`

- [ ] Task 4: Update Lambda function role references
  - File: `infra/aws/cloudformation/templates/api-gw-infra.yaml`
  - Action: Change `Role:` property in each Lambda function:
    - `SqsSizeFunction` (line 73): `Role: !GetAtt LambdaExecutionRole.Arn` → `Role: !GetAtt SqsSizeExecutionRole.Arn`
    - `RdsManagerFunction` (line 100): `Role: !GetAtt LambdaExecutionRole.Arn` → `Role: !GetAtt RdsManagerExecutionRole.Arn`
    - `Ec2ManagerFunction` (line 126): `Role: !GetAtt LambdaExecutionRole.Arn` → `Role: !GetAtt Ec2ManagerExecutionRole.Arn`

- [ ] Task 5: Remove shared `LambdaExecutionRole`
  - File: `infra/aws/cloudformation/templates/api-gw-infra.yaml`
  - Action: Delete the entire `LambdaExecutionRole` resource block (lines 21-66)
  - Notes: This must happen AFTER Tasks 1-4 so that the new roles are in place. CloudFormation handles this atomically — it creates new roles before deleting the old one during stack update.

- [ ] Task 6: Validate CloudFormation template
  - Action: Run `aws cloudformation validate-template --template-body file://infra/aws/cloudformation/templates/api-gw-infra.yaml`
  - Notes: Confirms YAML syntax and basic CloudFormation structure are valid.

- [ ] Task 7: Update architecture documentation
  - File: `docs/architecture-infra.md`
  - Action: Update the `api-gw-infra.yaml` row in the API Gateway table (line 158) to reflect that each Lambda now has its own IAM role instead of a shared role. Change description from mentioning "IAM Role" (singular) to "3 IAM Roles" (per-function). Add a note that roles follow least-privilege principle with resource-level scoping.

### Acceptance Criteria

- [ ] AC 1: Given the updated `api-gw-infra.yaml` template, when `aws cloudformation validate-template` is run, then it succeeds without errors.

- [ ] AC 2: Given the deployed stack, when inspecting `SqsSizeFunction` in AWS Console, then its execution role is `lenie-dev-sqs-size-role` and the role has ONLY CloudWatch Logs, SQS (`GetQueueAttributes` scoped to `lenie-dev-*` queues), and SSM permissions.

- [ ] AC 3: Given the deployed stack, when inspecting `RdsManagerFunction` in AWS Console, then its execution role is `lenie-dev-rds-manager-role` and the role has ONLY CloudWatch Logs, RDS (Start/Stop/Describe scoped to the specific DB instance from SSM), and SSM permissions.

- [ ] AC 4: Given the deployed stack, when inspecting `Ec2ManagerFunction` in AWS Console, then its execution role is `lenie-dev-ec2-manager-role` and the role has ONLY CloudWatch Logs, EC2 (Start/Stop scoped to the specific instance, Describe with `*`), and SSM permissions.

- [ ] AC 5: Given the deployed stack, when searching for the old `LambdaExecutionRole` in IAM, then it no longer exists (deleted by CloudFormation during stack update).

- [ ] AC 6: Given the deployed stack, when calling `GET /sqs/size` via API Gateway, then it returns the SQS queue size successfully (200 response).

- [ ] AC 7: Given the deployed stack, when calling `POST /database/start`, `POST /database/stop`, and `GET /database/status` via API Gateway, then each returns a successful response (Lambda can perform RDS operations).

- [ ] AC 8: Given the deployed stack, when calling `POST /vpn_server/start`, `POST /vpn_server/stop`, and `GET /vpn_server/status` via API Gateway, then each returns a successful response (Lambda can perform EC2 operations).

- [ ] AC 9: Given the updated `docs/architecture-infra.md`, when reviewing the api-gw-infra row, then it accurately describes per-function IAM roles with least-privilege scoping.

## Additional Context

### Dependencies

- Existing SSM Parameters must contain correct resource identifiers:
  - `/${ProjectCode}/${Environment}/database/name` — RDS instance identifier (used for RDS role scoping)
  - SSM parameter referenced by `OpenvpnEC2Name` CF parameter — EC2 instance ID (used for EC2 role scoping)
- No other templates reference the shared `LambdaExecutionRole` (confirmed — no cross-stack exports)
- CloudFormation stack uses `CAPABILITY_NAMED_IAM` (already configured in `deploy.sh`)
- The `deploy.sh` script automatically creates a new API Gateway deployment after updating `api-gw-infra` stack

### Testing Strategy

1. **Pre-deploy validation:** `aws cloudformation validate-template --template-body file://infra/aws/cloudformation/templates/api-gw-infra.yaml`
2. **Change-set preview:** `./deploy.sh -p lenie -s dev -t` — review the change-set to confirm:
   - 3 new IAM roles being created
   - 3 Lambda functions being updated (role reference change)
   - 1 old IAM role being deleted
3. **Deploy:** `./deploy.sh -p lenie -s dev` (auto-detects update for existing stack)
4. **Post-deploy verification:**
   - Verify each Lambda has its own role in AWS Console (IAM → Roles)
   - Test all 7 API endpoints via the React frontend or direct API calls:
     - `GET /sqs/size`
     - `POST /database/start`, `POST /database/stop`, `GET /database/status`
     - `POST /vpn_server/start`, `POST /vpn_server/stop`, `GET /vpn_server/status`
   - Verify old shared role no longer exists in IAM
5. **Rollback plan:** CloudFormation automatic rollback on stack update failure; manual rollback via `git revert` + redeploy

### Notes

- B-21 was identified during Epic 14 retrospective as increasingly urgent
- Original backlog mentioned 7 Lambda functions, but previous tasks reduced this to 3
- The 7 API Gateway endpoints are served by these 3 functions (multi-action pattern)
- CloudFormation handles the role swap atomically during stack update — new roles are created before the old one is deleted, so there is no downtime
- `ec2:DescribeInstances` requiring `Resource: '*'` is a known AWS limitation (not a security concern — it only allows reading instance metadata, not modifying resources)
- The `SqsSizeFunction` has a `DB_ID` environment variable — this appears to be a leftover from template copy-paste but does not affect IAM scoping (the function only needs SQS permissions at runtime)
