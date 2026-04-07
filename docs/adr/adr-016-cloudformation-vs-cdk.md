# ADR-016: CloudFormation as Primary IaC — Evaluate CDK for Future Comparison

**Date:** 2026-03-31
**Status:** Accepted (CloudFormation); Proposed (CDK evaluation)
**Decision Makers:** Ziutus

## Context

Project Lenie's AWS infrastructure is managed by **29 CloudFormation templates** deployed via a universal `deploy.sh` script. This setup was built incrementally across 3 infrastructure sprints (Feb–Mar 2026) and now covers the entire AWS stack: VPC, RDS, DynamoDB, SQS, S3, 11 Lambda functions, 2 API Gateways, Step Functions, CloudFront, ACM, and budget controls.

The project owner wants to evaluate **AWS CDK** as an alternative/complementary IaC tool for learning purposes and to make an informed long-term decision. The project also uses Terraform (VPC + bastion) and Kubernetes (Kustomize) as secondary IaC tools for comparison.

## Decision

1. **CloudFormation remains the primary IaC tool** for all production infrastructure.
2. **A CDK evaluation will be conducted** by reimplementing a self-contained subset of infrastructure (e.g., SQS → Lambda → DynamoDB pipeline) in CDK.
3. The evaluation is **non-urgent** — it will happen when the owner has bandwidth, after AWS restoration (see [aws-roadmap.md](aws-roadmap.md), Phase 5).
4. Both implementations (CF and CDK) will coexist in the repository for comparison.

## Rationale — Why CloudFormation Now

| Advantage | Detail |
|-----------|--------|
| **Battle-tested** | 29 templates, 3 sprints of refinement, universal deploy script |
| **No build step** | YAML is directly deployable — no compilation, no CDK bootstrap |
| **Full AWS coverage** | Every AWS feature available on day 1, no waiting for CDK construct updates |
| **Simple mental model** | Declarative — describe desired state, AWS figures out the rest |
| **No runtime dependency** | No Node.js/Python CDK library to manage, no `cdk synth` step |
| **Drift detection** | Native CloudFormation drift detection |

## Rationale — Why Evaluate CDK

| Advantage | Detail |
|-----------|--------|
| **Type safety** | TypeScript/Python constructs catch errors at compile time vs runtime |
| **L2/L3 constructs** | Higher-level abstractions encode AWS best practices (e.g., `Function` auto-creates IAM role, log group) |
| **Less boilerplate** | Equivalent infrastructure in ~60% fewer lines |
| **Testing** | Infrastructure testable with jest/pytest — assert on synthesized CloudFormation |
| **Reusable patterns** | Custom constructs shareable across projects |
| **AWS investment** | CDK is where AWS is investing most IaC development effort |

## Evaluation Plan

1. **Scope:** Reimplement the SQS + Lambda (`sqs-weblink-put-into`) + DynamoDB pipeline
2. **Language:** Python CDK (to stay in the project's primary language) or TypeScript (for stronger typing)
3. **Location:** `infra/aws/cdk/` alongside existing `infra/aws/cloudformation/`
4. **Comparison criteria:**
   - Lines of code for equivalent functionality
   - Developer experience (IDE support, error messages, documentation)
   - Deployment speed and reliability
   - Testing capabilities
   - Drift handling
   - Learning curve
5. **Tool support:** [AWS Serverless plugin](https://claude.com/plugins/aws-serverless) for Claude Code
6. **Output:** Findings documented in this ADR (update status to "Evaluated" with conclusions)

## Risks

- **CDK bootstrap** adds a CloudFormation stack (`CDKToolkit`) per account/region — minor but permanent overhead.
- **Version drift** — CDK library updates may introduce breaking changes; CF YAML is stable.
- **Two systems to maintain** during evaluation period — mitigated by limiting CDK scope to one pipeline.
- **CDK-generated CloudFormation** is verbose and hard to debug when things go wrong — you're debugging generated code, not code you wrote.

## Consequences

- CloudFormation templates in `infra/aws/cloudformation/` remain the source of truth.
- No CDK work until Phase 5 of the [AWS Roadmap](aws-roadmap.md) — after AWS restoration and CI/CD.
- When CDK evaluation starts, install the AWS Serverless plugin for Claude Code.
- Decision will be updated with evaluation findings — possible outcomes: (a) stay with CF, (b) migrate to CDK, (c) use CDK for new infra / CF for existing.

## References

- [AWS Roadmap](aws-roadmap.md) — full infrastructure development plan
- [Technology Choices](technology-choices.md) — current tool rationale
- [System Evolution](system-evolution.md) — infrastructure history
- [CloudFormation deploy docs](../infra/aws/cloudformation/CLAUDE.md) — operational guide
