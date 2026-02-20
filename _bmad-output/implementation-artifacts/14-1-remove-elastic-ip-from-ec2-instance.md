# Story 14.1: Remove Elastic IP from EC2 Instance

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **developer**,
I want to remove the Elastic IP from the EC2 CloudFormation template and rely on dynamic public IP with Route53 DNS updates,
so that unnecessary EIP idle charges (~$3.65/month) are eliminated while maintaining DNS-based access to the instance.

## Acceptance Criteria

1. **Given** `infra/aws/cloudformation/templates/ec2-lenie.yaml` contains `ElasticIP` (AWS::EC2::EIP) resource, **When** the developer removes it, **Then** the resource definition is deleted entirely (no commented-out remnants).

2. **Given** `ec2-lenie.yaml` contains `EIPAssociation` (AWS::EC2::EIPAssociation) resource, **When** the developer removes it, **Then** the resource definition is deleted entirely.

3. **Given** `ec2-lenie.yaml` contains `Outputs.PublicIP` referencing the Elastic IP, **When** the developer removes the output, **Then** the `PublicIP` output is deleted entirely (nothing consumes this output).

4. **Given** the EC2 template is modified, **When** the developer runs cfn-lint validation, **Then** the template passes with zero errors.

5. **Given** `infra/aws/tools/aws_ec2_route53.py` exists, **When** the developer reviews its behavior, **Then** the script correctly retrieves the EC2 dynamic public IP and updates the Route53 A record on each instance start.

6. **Given** `infra/aws/cloudformation/templates/vpc.yaml` defines public subnets, **When** the developer verifies `MapPublicIpOnLaunch: 'true'` (lines 83, 98), **Then** EC2 instances launched in these subnets receive a dynamic public IP automatically.

## Tasks / Subtasks

- [x] Task 1: Remove ElasticIP resource from ec2-lenie.yaml (AC: #1)
  - [x] Delete lines 71-80 (`ElasticIP` resource block — `AWS::EC2::EIP` with tags)
  - [x] Ensure no blank line remnants or comments remain where the resource was
- [x] Task 2: Remove EIPAssociation resource from ec2-lenie.yaml (AC: #2)
  - [x] Delete lines 82-86 (`EIPAssociation` resource block — `AWS::EC2::EIPAssociation`)
- [x] Task 3: Remove PublicIP output from ec2-lenie.yaml (AC: #3)
  - [x] Delete lines 119-121 (`Outputs.PublicIP` referencing `!Ref ElasticIP`)
  - [x] If the Outputs section becomes empty after this removal, remove the `Outputs:` key entirely
- [x] Task 4: Validate modified template (AC: #4)
  - [x] Run `cfn-lint infra/aws/cloudformation/templates/ec2-lenie.yaml`
  - [x] Ensure zero errors
- [x] Task 5: Verify Route53 dynamic DNS update script (AC: #5)
  - [x] Read `infra/aws/tools/aws_ec2_route53.py` — confirm it uses `describe_instances` to get `PublicIpAddress` (NOT ElasticIP)
  - [x] Confirm retry logic exists for cases where public IP is not yet available
  - [x] No code changes needed — verification only
- [x] Task 6: Verify VPC subnet configuration (AC: #6)
  - [x] Read `infra/aws/cloudformation/templates/vpc.yaml` — confirm `MapPublicIpOnLaunch: 'true'` on PublicSubnet1 (line 83) and PublicSubnet2 (line 98)
  - [x] No code changes needed — verification only

## Dev Notes

### Architecture Compliance

**CloudFormation Resource Removal Pattern (from Sprint 4 Architecture):**
- Delete resource blocks entirely — no commented-out remnants
- Delete associated outputs that reference removed resources
- Do NOT add placeholder comments (e.g., `# Removed: ElasticIP`) — git history provides this
- Do NOT add replacement resources unless explicitly required by a FR

**Anti-patterns (NEVER do):**
- Leaving commented-out resource definitions
- Adding `Condition: Never` instead of removing
- Adding `DeletionPolicy: Retain` to resources being removed
- Replacing removed output with a new dynamic equivalent when nothing consumes it (FR3 says remove entirely)

**Gen 2+ Canonical Template Pattern** remains in effect — do not modify any other resources in the template. This is a removal-only change.

### Critical Technical Context

**What is being removed:**
```yaml
# Lines 71-80 — ElasticIP resource
ElasticIP:
  Type: 'AWS::EC2::EIP'
  Properties:
    Tags:
      - Key: Name
        Value: !Sub '${ProjectCode}-${Environment}-eip'
      - Key: Environment
        Value: !Ref Environment
      - Key: Project
        Value: !Ref ProjectCode

# Lines 82-86 — EIPAssociation resource
EIPAssociation:
  Type: 'AWS::EC2::EIPAssociation'
  Properties:
    InstanceId: !Ref EC2Instance
    EIP: !Ref ElasticIP

# Lines 119-121 — PublicIP output
PublicIP:
  Description: 'The Public IP address of the instance'
  Value: !Ref ElasticIP
```

**Why removal is safe:**
1. **Dynamic IP availability:** vpc.yaml PublicSubnet1 and PublicSubnet2 both have `MapPublicIpOnLaunch: 'true'` — EC2 instances get a public IP automatically when launched in these subnets.
2. **DNS updates:** `aws_ec2_route53.py` retrieves the dynamic public IP via `ec2.describe_instances()` → `PublicIpAddress` field (NOT via ElasticIP). It has retry logic (10s wait) for cases where IP is not yet available. Updates Route53 A record with UPSERT and TTL 300s.
3. **No consumers:** Nothing references `Outputs.PublicIP` — Route53 is updated via `aws_ec2_route53.py`, not via CF cross-stack references.
4. **EC2 usage pattern:** Instance is typically stopped (started on-demand for RDS access). Idle EIP costs ~$3.65/month.

**CloudFormation deployment note:** Removing the ElasticIP resource will cause CloudFormation to release the Elastic IP address. The EC2 instance will need to be stopped and started (or restarted) to pick up a new dynamic public IP. After restart, run `aws_ec2_route53.py` to update DNS.

### What NOT to change

- Do NOT modify `infra/aws/tools/aws_ec2_route53.py` — it already works with dynamic IPs
- Do NOT modify `infra/aws/cloudformation/templates/vpc.yaml` — subnet config is correct
- Do NOT add a new output for dynamic IP — nothing needs it (FR3 explicitly says remove entirely)
- Do NOT modify any other resources in `ec2-lenie.yaml` (EC2Instance, SecurityGroup, etc.)
- Do NOT update `deploy.ini` — `ec2-lenie.yaml` stays in deployment order

### File Structure

Only one file modified:

| File | Action | Description |
|------|--------|-------------|
| `infra/aws/cloudformation/templates/ec2-lenie.yaml` | MOD | Remove 3 blocks: ElasticIP, EIPAssociation, Outputs.PublicIP |

Verification-only files (read, no changes):

| File | Verification |
|------|-------------|
| `infra/aws/cloudformation/templates/vpc.yaml` | MapPublicIpOnLaunch: 'true' on both public subnets |
| `infra/aws/tools/aws_ec2_route53.py` | Uses dynamic IP from describe_instances, not EIP |

### Testing Requirements

1. **cfn-lint validation:** `cfn-lint infra/aws/cloudformation/templates/ec2-lenie.yaml` — zero errors
2. **Template validation:** `aws cloudformation validate-template --template-body file://infra/aws/cloudformation/templates/ec2-lenie.yaml` — valid
3. **Manual verification:** Confirm template still has `EC2Instance`, `LaunchTemplate`, and remaining resources intact

### Previous Story Intelligence (Epic 13)

**From Story 13.1 (zip_to_s3.sh safety):**
- Bash flag parsing pattern: for/case loop before `$#` check
- Minimal change approach: only additive, match existing style
- Code review caught missing env var validation — be thorough

**From Story 13.2 (CRLF verification):**
- Verification-driven closure pattern: verify existing work, document findings
- Reference root causes, not symptoms

**From Sprint 4 Git History:**
- Latest commits are Sprint 4 planning and Epic 13 stories
- No recent changes to `ec2-lenie.yaml` in current sprint

### Project Structure Notes

- `infra/aws/cloudformation/templates/ec2-lenie.yaml` is in Layer 5 (Compute) of deploy.ini
- EC2 instance is deployed in `PublicSubnet1` (line 34 of ec2-lenie.yaml)
- Sprint 4 architecture confirms B-4 (this story) is independent of B-5 (Lambda naming) — can be done in parallel

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 14, Story 14.1]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, EIP Removal Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md — Sprint 4, CF Resource Removal Pattern]
- [Source: _bmad-output/planning-artifacts/prd.md — FR1-FR5, NFR2-NFR4, NFR6]
- [Source: infra/aws/cloudformation/templates/ec2-lenie.yaml — lines 71-86, 119-121]
- [Source: infra/aws/cloudformation/templates/vpc.yaml — lines 83, 98]
- [Source: infra/aws/tools/aws_ec2_route53.py — get_instance_public_ip(), update_route53_record()]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

No issues encountered during implementation.

### Completion Notes List

- Removed `ElasticIP` (AWS::EC2::EIP) resource block entirely from ec2-lenie.yaml — no commented-out remnants
- Removed `EIPAssociation` (AWS::EC2::EIPAssociation) resource block entirely
- Removed `Outputs.PublicIP` referencing ElasticIP — `Outputs` section retained with remaining `InstanceId` output
- cfn-lint validation passed with zero errors
- Verified `aws_ec2_route53.py` uses `describe_instances()` → `PublicIpAddress` (dynamic IP, not EIP) with 10s retry logic
- Verified `vpc.yaml` PublicSubnet1 (line 83) and PublicSubnet2 (line 98) both have `MapPublicIpOnLaunch: 'true'`
- Template retains all other resources unchanged: EC2Instance, InstanceSecurityGroup, InstanceRole, InstanceProfile

### Implementation Plan

Removal-only change following CloudFormation Resource Removal Pattern from Sprint 4 Architecture. Three blocks removed, two verification-only checks performed. No new resources or outputs added.

### File List

| File | Action | Description |
|------|--------|-------------|
| `infra/aws/cloudformation/templates/ec2-lenie.yaml` | MOD | Removed ElasticIP, EIPAssociation resources and PublicIP output |

## Change Log

| Date | Change | Story |
|------|--------|-------|
| 2026-02-20 | Removed Elastic IP and EIP Association resources from EC2 CloudFormation template to eliminate ~$3.65/month idle charges; verified Route53 DNS update script and VPC subnet config support dynamic public IP | 14-1 |
