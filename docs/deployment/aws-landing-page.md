# AWS deployment: landing page

The production landing page is a static Next.js export hosted in S3 and served through CloudFront at `https://www.lenie-ai.eu`.

## Prerequisites

Use the AWS CLI with credentials that can read SSM parameters, write to the landing bucket, and create CloudFront invalidations. The production region is `us-east-1`.

## Deploy

From `web_landing_page/`:

```powershell
npm ci
npm run build
```

The build must finish with the static routes generated in `out/`. Resolve the production resources from SSM instead of hardcoding them:

```powershell
$bucket = aws ssm get-parameter --region us-east-1 --name /lenie/prod/s3/landing-web/name --query Parameter.Value --output text
$distribution = aws ssm get-parameter --region us-east-1 --name /lenie/prod/cloudfront/landing/id --query Parameter.Value --output text
```

Upload the complete export and remove stale files:

```powershell
aws s3 sync out "s3://$bucket" --delete --region us-east-1
```

Invalidate CloudFront:

```powershell
aws cloudfront create-invalidation --distribution-id $distribution --paths '/*'
```

Wait until the invalidation is complete, then verify `https://www.lenie-ai.eu` and at least one nested route such as `/about/`.

## Infrastructure changes

CloudFormation infrastructure is separate from the static upload. If the bucket or distribution must be created or changed, run from `infra/aws/cloudformation/`:

```bash
./deploy.sh -p lenie -s landing-prod
```

The normal content release only needs `npm run build`, `aws s3 sync`, and the CloudFront invalidation.

## Notes

- `next.config.mjs` sets `output: 'export'`; deploy `out/`, not `.next/`.
- `--delete` keeps S3 aligned with the generated export and removes obsolete assets.
- Keep the CloudFront invalidation ID for troubleshooting and audit history.
