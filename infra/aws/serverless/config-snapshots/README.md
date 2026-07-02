# Lambda Configuration Snapshots

Sanitized configuration snapshots (runtime, handler, layers, timeout, memory, env **key names only** — no values, IAM role ARN) taken 2026-07-02 during the AWS serverless decommission audit.

Purpose: reference for restoring or auditing functions later. See [docs/aws-serverless-restoration.md](../../../../docs/aws-serverless-restoration.md).

Env var **values** are not stored here — they live in SSM Parameter Store under `/lenie/dev/*` (read them via `python scripts/env_to_vault.py ssm get --env dev <KEY>`).
