# AWS Troubleshooting

Common issues encountered when working with AWS services in this project.

## API Gateway + Lambda

### Malformed Lambda proxy response

**Error in API Gateway logs:**
```
Execution failed due to configuration error: Malformed Lambda proxy response
```

**Cause:** The response returned by the Lambda function is not properly formatted for API Gateway. API Gateway expects the Lambda response to follow the AWS Lambda proxy response model.

**Required fields:**
- `statusCode` — HTTP status code as an integer
- `body` — Response body as a **string** (use `json.dumps()` for JSON data)
- `headers` — JSON object with key-value pairs as HTTP headers

**Correct response example (Python):**

```python
{
    "statusCode": 200,
    "body": json.dumps({
        "message": "hello world",
    }),
    "headers": {
        "Content-Type": "application/json",
    }
}
```

> **Tip:** The most common mistake is returning `body` as a dict/object instead of a string. Always use `json.dumps()` in Python or `JSON.stringify()` in JavaScript.

## Lambda — No module named 'library'

**Error in Step Functions / Lambda logs:**
```
Unable to import module 'lambda_function': No module named 'library'
```

**Cause:** The Lambda function imports `backend/library/` but is classified as a "simple" function in `function_list_cf.txt`. Simple functions are packaged as a single `lambda_function.py` without the `library/` directory.

**Fix:** Move the function name from `function_list_cf.txt` (simple) to `function_list_cf_app.txt` (app). App functions include `backend/library/` in their zip package. Then rebuild: `./zip_to_s3.sh app`.

**Note:** The `zip_to_s3.sh` script uses the source directory name (e.g., `sqs-into-rds`) to generate the zip file name (e.g., `lenie-dev-sqs-into-rds.zip`), but the CloudFormation function name may differ (e.g., `lenie-dev-sqs-to-rds-lambda`). If `aws lambda update-function-code` in the script fails with "function not found", manually run:
```bash
aws lambda update-function-code --function-name <actual-cf-name> --s3-bucket lenie-dev-cloudformation --s3-key <zip-name>.zip
```

## Lambda — Password authentication failed for PostgreSQL user

**Error:**
```
FATAL: password authentication failed for user "lenie"
```

**Possible causes:**

1. **User does not exist in RDS** — The RDS master user is `postgres`, not `lenie`. The `lenie` user must be created manually in PostgreSQL. Docker init scripts (`backend/database/init/`) only run in Docker, not on RDS.

2. **Password mismatch** — The password in Secrets Manager (`/${ProjectCode}/${Environment}/rds/password`) may not match the PostgreSQL user's password. Secrets Manager holds the secret, but changing it does NOT automatically update the database user's password.

3. **Master user vs application user** — `aws rds modify-db-instance --master-user-password` changes the `postgres` (master) user's password, NOT the `lenie` (application) user's password. To change the `lenie` user's password, connect as `postgres` and run `ALTER USER lenie WITH PASSWORD '...'`.

**Creating the application user on RDS:**
```sql
-- Connect as postgres to the lenie database
CREATE USER lenie WITH PASSWORD '<password-from-secrets-manager>';
GRANT ALL PRIVILEGES ON DATABASE lenie TO lenie;
GRANT USAGE ON SCHEMA public TO lenie;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO lenie;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO lenie;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO lenie;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO lenie;
```

## Lambda — SSL connection required

**Error:**
```
no pg_hba.conf entry for host "...", user "lenie", database "lenie", no encryption
```

**Cause:** RDS requires SSL connections but the Lambda's psycopg2 connects without encryption by default.

**Fix:** Add `POSTGRESQL_SSLMODE: require` environment variable to the Lambda's CloudFormation template. The backend library (`stalker_web_document_db.py` and `stalker_web_documents_db_postgresql.py`) reads `POSTGRESQL_SSLMODE` and passes it to `psycopg2.connect()`.

## MSYS Path Conversion on Windows Git Bash

**Symptom:** AWS CLI commands with paths like `/lenie/dev/rds/password` get mangled (e.g., converted to `C:/msys64/lenie/dev/rds/password`).

**Fix:** Prefix commands with `MSYS_NO_PATHCONV=1`:
```bash
MSYS_NO_PATHCONV=1 aws secretsmanager get-secret-value --secret-id /lenie/dev/rds/password
```

## Special Characters in Passwords via Shell

**Symptom:** `aws rds modify-db-instance --master-user-password` sets a garbled password when the password contains shell metacharacters (`$`, `^`, `{`, `}`, `(`, `)`, etc.).

**Fix:** Use Python `subprocess.run()` with a list of arguments (no shell interpretation) instead of bash string interpolation:
```python
import subprocess
subprocess.run(['aws', 'rds', 'modify-db-instance', '--db-instance-identifier', 'lenie-dev',
                '--master-user-password', password, '--apply-immediately', '--region', 'us-east-1'])
```
