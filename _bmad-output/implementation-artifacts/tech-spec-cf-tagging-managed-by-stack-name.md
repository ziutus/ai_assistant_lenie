---
title: 'Add ManagedBy and StackName tags to all CloudFormation resources'
slug: 'cf-tagging-managed-by-stack-name'
created: '2026-02-25'
status: 'ready-for-dev'
stepsCompleted: [1, 2, 3, 4]
tech_stack: [CloudFormation, YAML]
files_to_modify:
  - infra/aws/cloudformation/templates/1-domain-route53.yaml
  - infra/aws/cloudformation/templates/acm-certificates.yaml
  - infra/aws/cloudformation/templates/api-gw-account.yaml
  - infra/aws/cloudformation/templates/api-gw-app.yaml
  - infra/aws/cloudformation/templates/api-gw-custom-domain.yaml
  - infra/aws/cloudformation/templates/api-gw-infra.yaml
  - infra/aws/cloudformation/templates/cloudfront-app.yaml
  - infra/aws/cloudformation/templates/cloudfront-app2.yaml
  - infra/aws/cloudformation/templates/cloudfront-landing.yaml
  - infra/aws/cloudformation/templates/dynamodb-documents.yaml
  - infra/aws/cloudformation/templates/ec2-lenie.yaml
  - infra/aws/cloudformation/templates/env-setup.yaml
  - infra/aws/cloudformation/templates/helm.yaml
  - infra/aws/cloudformation/templates/lambda-layer-lenie-all.yaml
  - infra/aws/cloudformation/templates/lambda-layer-openai.yaml
  - infra/aws/cloudformation/templates/lambda-layer-psycopg2.yaml
  - infra/aws/cloudformation/templates/lambda-rds-start.yaml
  - infra/aws/cloudformation/templates/lambda-weblink-put-into-sqs.yaml
  - infra/aws/cloudformation/templates/lenie-launch-template.yaml
  - infra/aws/cloudformation/templates/rds.yaml
  - infra/aws/cloudformation/templates/s3-app-web.yaml
  - infra/aws/cloudformation/templates/s3-app2-web.yaml
  - infra/aws/cloudformation/templates/s3-cloudformation.yaml
  - infra/aws/cloudformation/templates/s3-landing-web.yaml
  - infra/aws/cloudformation/templates/s3-website-content.yaml
  - infra/aws/cloudformation/templates/s3.yaml
  - infra/aws/cloudformation/templates/secrets.yaml
  - infra/aws/cloudformation/templates/security-groups.yaml
  - infra/aws/cloudformation/templates/sqs-application-errors.yaml
  - infra/aws/cloudformation/templates/sqs-documents.yaml
  - infra/aws/cloudformation/templates/sqs-to-rds-lambda.yaml
  - infra/aws/cloudformation/templates/sqs-to-rds-step-function.yaml
  - infra/aws/cloudformation/templates/url-add.yaml
  - infra/aws/cloudformation/templates/vpc.yaml
code_patterns:
  - 'List-style tags: - Key: X / Value: Y (all resources except SSM::Parameter)'
  - 'Map-style tags: Key: Value (SSM::Parameter only)'
  - 'Environment and Project tags present on ~111 resources (114 total taggable including 3 missing tags)'
  - 'Tag values use !Ref Environment, !Ref ProjectCode, or literal "lenie"'
  - '!Ref AWS::StackName pseudo-parameter for dynamic stack name'
test_patterns:
  - 'aws cloudformation validate-template for each modified template'
---

# Tech-Spec: Add ManagedBy and StackName tags to all CloudFormation resources

**Created:** 2026-02-25

## Overview

### Problem Statement

The project uses multiple IaC tools (CloudFormation, Terraform). When viewing resources in the AWS console or via API, there is no way to tell which tool created a resource or which specific CloudFormation stack manages it. This makes auditing, cost allocation, and resource lifecycle management harder.

### Solution

Add two new tags to every taggable resource across all CloudFormation templates:
- `ManagedBy: CloudFormation` — identifies the IaC tool that created the resource
- `StackName: !Ref AWS::StackName` — dynamically resolves to the stack name (e.g. `lenie-dev-vpc`)

Also fix 3 resources that support tags but are currently missing them.

### Scope

**In Scope:**
- Add `ManagedBy` and `StackName` tags to all ~114 taggable resources across 34 CloudFormation templates
- Fix 3 resources missing tags entirely: CloudWatchRoleArnParameter (SSM), ApiStage (api-gw-app), ApiStage (api-gw-infra)

**Out of Scope:**
- Resources that don't support tags in CloudFormation (~30 resources including BucketPolicy, Lambda Permission, Route53 RecordSet, OAC, Deployment, BasePathMapping, GatewayResponse, LayerVersion, SecretTargetAttachment, OAI, Budget, InstanceProfile, SNS::Subscription, Scheduler::Schedule, Organizations::*, IdentityStore::*)
- Templates with zero taggable resources: organization.yaml, scp-block-sso-creation.yaml, scp-only-allowed-reginos.yaml, scp-block-all.yaml, identityStore.yaml, budget.yaml (AWS::Budgets::Budget does not support Tags in CloudFormation)
- Changing existing tag values or key names
- Deploying the changes to AWS (separate step after merge)

## Context for Development

### Codebase Patterns

**List-style tags** (all resources except SSM::Parameter):
```yaml
Tags:
  - Key: Environment
    Value: !Ref Environment
  - Key: Project
    Value: !Ref ProjectCode
```
Append:
```yaml
  - Key: ManagedBy
    Value: CloudFormation
  - Key: StackName
    Value: !Ref 'AWS::StackName'
```

**HostedZoneTags** (Route53 HostedZone only — uses `HostedZoneTags`, NOT `Tags`):
```yaml
HostedZoneTags:
  - Key: Environment
    Value: !Ref Environment
  - Key: Project
    Value: lenie
```
Append:
```yaml
  - Key: ManagedBy
    Value: CloudFormation
  - Key: StackName
    Value: !Ref 'AWS::StackName'
```

**Map-style tags** (SSM::Parameter only):
```yaml
Tags:
  Environment: !Ref Environment
  Project: !Ref ProjectCode
```
Append:
```yaml
  ManagedBy: CloudFormation
  StackName: !Ref 'AWS::StackName'
```

### Files to Reference

| File | Taggable Resources | Notes |
| ---- | ------- | ----- |
| 1-domain-route53.yaml | 1 (HostedZone) | Uses `HostedZoneTags` (NOT `Tags`); DISABLED in deploy.ini |
| acm-certificates.yaml | 2 (Certificate, SSM) | |
| api-gw-account.yaml | 2 (IAM Role, SSM) | SSM missing tags — FIX |
| api-gw-app.yaml | 5 (RestApi, Stage, 3x SSM) | Stage missing tags — FIX |
| api-gw-custom-domain.yaml | 4 (Certificate, DomainName, 2x SSM) | |
| api-gw-infra.yaml | 10 (3x IAM, 3x Lambda, RestApi, Stage, 2x SSM) | Stage missing tags — FIX |
| cloudfront-app.yaml | 3 (Distribution, 2x SSM) | |
| cloudfront-app2.yaml | 3 (Distribution, 2x SSM) | |
| cloudfront-landing.yaml | 4 (Certificate, Distribution, 2x SSM) | |
| dynamodb-documents.yaml | 3 (Table, 2x SSM) | |
| ec2-lenie.yaml | 3 (Instance, SG, IAM Role) | InstanceProfile not taggable |
| env-setup.yaml | 1 (SSM) | |
| helm.yaml | 2 (Bucket, Distribution) | |
| lambda-layer-lenie-all.yaml | 1 (SSM) | LayerVersion not taggable |
| lambda-layer-openai.yaml | 1 (SSM) | LayerVersion not taggable |
| lambda-layer-psycopg2.yaml | 1 (SSM) | LayerVersion not taggable |
| lambda-rds-start.yaml | 2 (IAM Role, Lambda) | |
| lambda-weblink-put-into-sqs.yaml | 2 (IAM Role, Lambda) | |
| lenie-launch-template.yaml | 3 (LaunchTemplate, 2x SSM) | |
| rds.yaml | 3 (DB, SubnetGroup, SG) | |
| s3-app-web.yaml | 4 (Bucket, 3x SSM) | |
| s3-app2-web.yaml | 4 (Bucket, 3x SSM) | |
| s3-cloudformation.yaml | 2 (Bucket, SSM) | |
| s3-landing-web.yaml | 4 (Bucket, 3x SSM) | |
| s3-website-content.yaml | 3 (Bucket, 2x SSM) | |
| s3.yaml | 1 (Bucket) | |
| secrets.yaml | 2 (Secret, SSM) | |
| security-groups.yaml | 1 (SG) | |
| sqs-application-errors.yaml | 3 (Queue, Topic, SSM) | Subscription not taggable |
| sqs-documents.yaml | 3 (Queue, 2x SSM) | |
| sqs-to-rds-lambda.yaml | 2 (Lambda, IAM Role) | |
| sqs-to-rds-step-function.yaml | 4 (2x IAM, LogGroup, StepFunction) | Scheduler not taggable |
| url-add.yaml | 3 (Lambda, LogGroup, IAM Role) | |
| vpc.yaml | 12 (VPC, 6 Subnets, IGW, RouteTable, 3x SSM) | |

### Technical Decisions

- Tag key `ManagedBy` (not `IaC` or `iac:tool`) — clear, human-readable
- Tag key `StackName` (not `aws:cloudformation:stack-name`) — `aws:` prefix is reserved by AWS
- `!Ref 'AWS::StackName'` used for StackName value — dynamic, always correct
- `ManagedBy` value is literal `CloudFormation` (not parameterized) — no reason to make it dynamic
- 3 resources with missing tags get full 4-tag set (Environment, Project, ManagedBy, StackName)
- ~15 resource types verified as not supporting tags in CF — no action (see Out of Scope list)
- Route53 HostedZone uses `HostedZoneTags` property, not `Tags` — different syntax
- Tag ordering convention: Environment, Project, ManagedBy, StackName (append new tags after existing ones)

## Implementation Plan

### Tasks

- [ ] Task 1: Fix 3 resources with missing tags (add full 4-tag set)
  - File: `infra/aws/cloudformation/templates/api-gw-account.yaml`
  - Action: Add `Tags` property to `CloudWatchRoleArnParameter` (SSM map-style) with Environment, Project, ManagedBy, StackName
  - File: `infra/aws/cloudformation/templates/api-gw-app.yaml`
  - Action: Add `Tags` property to `ApiStage` (list-style) with Environment, Project, ManagedBy, StackName
  - File: `infra/aws/cloudformation/templates/api-gw-infra.yaml`
  - Action: Add `Tags` property to `ApiStage` (list-style) with Environment, Project, ManagedBy, StackName

- [ ] Task 2: Add ManagedBy + StackName to simple templates (1-2 taggable resources each)
  - File: `infra/aws/cloudformation/templates/1-domain-route53.yaml`
  - Action: Append ManagedBy + StackName to MyHostedZone using `HostedZoneTags` property (NOT `Tags`). Template is DISABLED in deploy.ini but should still be updated for consistency.
  - File: `infra/aws/cloudformation/templates/env-setup.yaml`
  - Action: Append ManagedBy + StackName to CloudFormationSSMParameter (map-style)
  - File: `infra/aws/cloudformation/templates/s3.yaml`
  - Action: Append ManagedBy + StackName to MyS3Bucket (list-style)
  - File: `infra/aws/cloudformation/templates/security-groups.yaml`
  - Action: Append ManagedBy + StackName to MySecurityGroup (list-style)
  - File: `infra/aws/cloudformation/templates/helm.yaml`
  - Action: Append to HelmBucket, HelmDistribution (list-style)

- [ ] Task 3: Add tags to acm-certificates.yaml
  - Action: Append to CloudFrontCertificate (list-style), CloudFrontCertificateArnParameter (map-style)

- [ ] Task 4: Add tags to api-gw-account.yaml (existing tagged resource)
  - Action: Append ManagedBy + StackName to ApiGatewayCloudWatchRole (list-style)

- [ ] Task 5: Add tags to api-gw-app.yaml (existing tagged resources)
  - Action: Append to LenieApi (list-style), ApiGatewayIdParameter, ApiGatewayRootResourceIdParameter, ApiGatewayInvokeUrlParameter (map-style)

- [ ] Task 6: Add tags to api-gw-custom-domain.yaml
  - Action: Append to ApiCertificate, ApiDomainName (list-style), CustomDomainUrlParameter, CustomDomainCertificateArnParameter (map-style)

- [ ] Task 7: Add tags to api-gw-infra.yaml (existing tagged resources — ApiStage handled in Task 1)
  - Action: Append to SqsSizeExecutionRole, RdsManagerExecutionRole, Ec2ManagerExecutionRole, SqsSizeFunction, RdsManagerFunction, Ec2ManagerFunction, LenieApi (list-style), ApiGatewayInfraIdParameter, ApiGatewayInfraInvokeUrlParameter (map-style)

- [ ] Task 8: Add tags to cloudfront-app.yaml, cloudfront-app2.yaml, cloudfront-landing.yaml
  - Action: Append to Distribution resources (list-style), SSM parameters (map-style), Certificate in landing (list-style)

- [ ] Task 9: Add tags to dynamodb-documents.yaml
  - Action: Append to LenieDocumentsTable (list-style), DocumentsTableNameParameter, DocumentsTableArnParameter (map-style)

- [ ] Task 10: Add tags to ec2-lenie.yaml
  - Action: Append to EC2Instance, InstanceSecurityGroup, InstanceRole (list-style). Skip InstanceProfile (not taggable).

- [ ] Task 11: Add tags to lambda templates
  - File: `lambda-layer-lenie-all.yaml` — Append to LenieAllLayerArnParameter (map-style)
  - File: `lambda-layer-openai.yaml` — Append to LenieOpenaiLayerArnParameter (map-style)
  - File: `lambda-layer-psycopg2.yaml` — Append to Psycopg2LayerArnParameter (map-style)
  - File: `lambda-rds-start.yaml` — Append to RDSStartLambdaRole, RDSStartLambdaFunction (list-style)
  - File: `lambda-weblink-put-into-sqs.yaml` — Append to LambdaExecutionRole, MyLambdaFunction (list-style)

- [ ] Task 12: Add tags to lenie-launch-template.yaml
  - Action: Append to ApplicationLaunchTemplate (list-style), ApplicationLaunchTemplateParam, ApplicationLaunchTemplateLatestVersionParam (map-style)

- [ ] Task 13: Add tags to rds.yaml
  - Action: Append to MyDB, DbSubnetGroup, MyDatabaseSecurityGroup (list-style)

- [ ] Task 14: Add tags to S3 templates
  - File: `s3-app-web.yaml` — Append to AppWebBucket (list-style), 3x SSM (map-style)
  - File: `s3-app2-web.yaml` — Append to App2WebBucket (list-style), 3x SSM (map-style)
  - File: `s3-cloudformation.yaml` — Append to MyS3Bucket (list-style), SSM (map-style)
  - File: `s3-landing-web.yaml` — Append to LandingWebBucket (list-style), 3x SSM (map-style)
  - File: `s3-website-content.yaml` — Append to WebsiteContentBucket (list-style), 2x SSM (map-style)

- [ ] Task 15: Add tags to secrets.yaml
  - Action: Append to RDSPasswordSecret (list-style), RDSPasswordSecretArnParameter (map-style)

- [ ] Task 16: Add tags to SQS templates
  - File: `sqs-application-errors.yaml` — Append to LenieDevProblemsDLQ, LenieDevProblemsTopic (list-style), ProblemsDlqArnParameter (map-style). Skip EmailSubscription (not taggable).
  - File: `sqs-documents.yaml` — Append to LenieDocumentsSQS (list-style), SQSNameParameter, SQSUrlParameter (map-style)

- [ ] Task 17: Add tags to sqs-to-rds-lambda.yaml
  - Action: Append to MyLambdaFunction, LambdaExecutionRole (list-style)

- [ ] Task 18: Add tags to sqs-to-rds-step-function.yaml
  - Action: Append to StateMachineRole, StateMachineLogGroup, MyStateMachine, StepFunctionInvokerRole (list-style). Skip EventBridgeScheduler (not taggable).

- [ ] Task 19: Add tags to url-add.yaml
  - Action: Append to LenineUrlAddLambdaFunction, LenineUrlAddLogGroup, LambdaExecutionRole (list-style)

- [ ] Task 20: Add tags to vpc.yaml
  - Action: Append to LenieVPC, PublicSubnet1, PublicSubnet2, PrivateSubnet1, PrivateSubnet2, PrivateDBSubnet1, PrivateDBSubnet2, MyInternetGateway, MyRouteTable (list-style), LenieVPCParam, DataSubnetBIdParam, DataSubnetBIdParam2 (map-style)

- [ ] Task 21: Validate all 34 modified templates
  - Action: Run `aws cloudformation validate-template --template-body file://templates/<name>.yaml` for each modified template
  - Full WSL command: `wsl bash -c "cd /mnt/c/Users/ziutus/git/_lenie-all/lenie-server-2025/infra/aws/cloudformation && for f in templates/*.yaml; do echo \"Validating $f...\"; aws cloudformation validate-template --template-body file://$f > /dev/null && echo '  OK' || echo '  FAILED'; done"`
  - Notes: Must be run via WSL (Git Bash/MSYS breaks `file://` paths)

### Acceptance Criteria

- [ ] AC1: Given any CloudFormation template in `infra/aws/cloudformation/templates/`, when a resource supports the `Tags` property, then it has `ManagedBy: CloudFormation` tag (list-style or map-style as appropriate)
- [ ] AC2: Given any CloudFormation template in `infra/aws/cloudformation/templates/`, when a resource supports the `Tags` property, then it has `StackName: !Ref 'AWS::StackName'` tag (list-style or map-style as appropriate)
- [ ] AC3: Given the 3 resources previously missing tags (CloudWatchRoleArnParameter, ApiStage in api-gw-app, ApiStage in api-gw-infra), when modified, then they have all 4 standard tags: Environment, Project, ManagedBy, StackName
- [ ] AC4: Given all 34 modified templates, when validated with `aws cloudformation validate-template`, then all templates pass validation without errors
- [ ] AC5: Given all modified templates, when searching for `ManagedBy` with grep, the count of occurrences matches the total number of taggable resources (~114). Verification: `grep -r "ManagedBy" infra/aws/cloudformation/templates/ | wc -l` should equal ~114

## Additional Context

### Dependencies

None — pure template modification, no code changes.

### Testing Strategy

1. Run `aws cloudformation validate-template` on all 34 modified templates via WSL
2. Visual spot-check of 3-4 templates to verify correct tag format (list vs map vs HostedZoneTags)
3. Run `grep -c "ManagedBy" infra/aws/cloudformation/templates/*.yaml | grep -v ':0$'` to verify tag presence
4. Optionally deploy one small stack (e.g. `env-setup.yaml`) to verify tags appear in AWS console
5. For API Gateway stacks: use change-set mode first (`deploy.sh -p lenie -s dev -t`) to preview changes before applying

### Rollback

- Tag additions are non-destructive in-place updates — rollback by reverting git commit and redeploying
- For API Gateway Stage: if unexpected replacement detected in change-set, abort and investigate before applying

### Notes

- SSM::Parameter uses map-style tags (`Key: Value`), all other resources use list-style (`- Key: X, Value: Y`)
- Route53 HostedZone uses `HostedZoneTags` property (NOT `Tags`) — this is a Route53-specific property name
- Some templates use `!Ref ProjectCode`, others use literal `lenie` for Project tag — this inconsistency is out of scope for this task
- `aws:cloudformation:stack-name` is automatically added by AWS in some cases, but our explicit `StackName` tag ensures visibility regardless of stack settings
- Templates with zero taggable resources are not modified: organization.yaml, scp-block-sso-creation.yaml, scp-only-allowed-reginos.yaml, scp-block-all.yaml, identityStore.yaml, budget.yaml
- Tag updates are in-place modifications (not resource replacements) — safe for all resource types
- High-risk item: API Gateway Stage resources (`api-gw-app.yaml`, `api-gw-infra.yaml`) — adding tags is a safe update, but use change-set mode (`deploy.sh -t`) for first deployment to verify no replacement
- `1-domain-route53.yaml` is DISABLED in deploy.ini (zone managed by legacy stack `lenie-domain-route53-definition`) — update template for consistency but no deployment needed
- `s3-landing-web.yaml` and `cloudfront-landing.yaml` are in `[landing-prod]` section — deployed separately via `deploy.sh -s landing-prod`, not with `-s dev`
- Tag ordering convention: always append ManagedBy and StackName after existing tags (Environment, Project)
- Git workflow: create a feature branch (e.g. `feat/cf-tagging-managed-by-stack-name`) before committing changes
