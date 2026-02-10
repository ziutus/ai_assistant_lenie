# AWS Infrastructure - DEV Environment

Overview of all AWS resources created by CloudFormation for the **DEV** environment of Project Lenie.

## Directory Structure

```
infra/aws/
├── cloudformation/
│   ├── templates/          # CloudFormation YAML templates
│   ├── parameters/dev/     # DEV environment parameter files
│   ├── step_functions/     # Step Functions definition (JSON)
│   └── apigw/              # OpenAPI specification (JSON)
├── eks/                    # EKS cluster configurations
├── serverless/             # Lambda function source code
├── terraform/              # Terraform IaC (alternative)
└── tools/                  # Helper scripts
```

## Resource Summary

| Category              | Count | Details                                      |
|-----------------------|-------|----------------------------------------------|
| CloudFormation Stacks | 27    | Templates in `cloudformation/templates/`     |
| Lambda Functions      | 11    | Python 3.11 runtime                          |
| API Gateway APIs      | 3     | app, infra, chrome-extension                 |
| API Endpoints         | 20+   | REST (REGIONAL)                              |
| SQS Queues            | 2     | documents, problems-dlq                      |
| SNS Topics            | 1     | problems notifications                       |
| RDS Instances         | 1     | PostgreSQL, db.t3.micro                      |
| DynamoDB Tables       | 1     | documents (PAY_PER_REQUEST)                  |
| S3 Buckets            | 2     | video-to-text, cloudformation artifacts      |
| EC2 Instances         | 1     | t4g.micro (ARM64)                            |
| Step Functions        | 1     | sqs-to-rds orchestration                     |
| VPC Subnets           | 6     | 2 public, 2 private, 2 DB private            |
| Budgets               | 1     | $20/month with alerts                        |

---

## 1. Networking & Base Infrastructure

### 1.1 Route 53 (`1-domain-route53.yaml`)

| Resource          | Type                          | Details              |
|-------------------|-------------------------------|----------------------|
| MyHostedZone      | AWS::Route53::HostedZone      | Domain: lenie-ai.eu  |

### 1.2 VPC (`vpc.yaml`)

| Resource                            | Type                                     | Details                    |
|-------------------------------------|------------------------------------------|----------------------------|
| LenieVPC                            | AWS::EC2::VPC                            | CIDR: 10.0.0.0/16         |
| PublicSubnet1                       | AWS::EC2::Subnet                         | 10.0.1.0/24, AZ-0, public |
| PublicSubnet2                       | AWS::EC2::Subnet                         | 10.0.2.0/24, AZ-1, public |
| PrivateSubnet1                      | AWS::EC2::Subnet                         | 10.0.3.0/24, AZ-0         |
| PrivateSubnet2                      | AWS::EC2::Subnet                         | 10.0.4.0/24, AZ-1         |
| PrivateDBSubnet1                    | AWS::EC2::Subnet                         | 10.0.5.0/24, AZ-0         |
| PrivateDBSubnet2                    | AWS::EC2::Subnet                         | 10.0.6.0/24, AZ-1         |
| MyInternetGateway                   | AWS::EC2::InternetGateway                | -                          |
| AttachGateway                       | AWS::EC2::VPCGatewayAttachment           | -                          |
| MyRouteTable                        | AWS::EC2::RouteTable                     | -                          |
| MyRoute                             | AWS::EC2::Route                          | 0.0.0.0/0 → IGW           |
| PublicSubnet1RouteTableAssociation  | AWS::EC2::SubnetRouteTableAssociation    | -                          |
| PublicSubnet2RouteTableAssociation  | AWS::EC2::SubnetRouteTableAssociation    | -                          |
| LenieVPCParam                       | AWS::SSM::Parameter                      | Stores VPC ID              |
| DataSubnetBIdParam                  | AWS::SSM::Parameter                      | Stores DataSubnetA ID      |
| DataSubnetBIdParam2                 | AWS::SSM::Parameter                      | Stores DataSubnetB ID      |

### 1.3 Environment Setup (`env-setup.yaml`)

| Resource                     | Type                    | Details                                            |
|------------------------------|-------------------------|----------------------------------------------------|
| CloudFormationSSMParameter   | AWS::SSM::Parameter     | `/lenie/dev/python/lambda-runtime-version` = python3.11 |

### 1.4 Security Groups (`security-groups.yaml`)

| Resource          | Type                       | Details                          |
|-------------------|----------------------------|----------------------------------|
| MySecurityGroup   | AWS::EC2::SecurityGroup    | SSH (port 22), restricted CIDRs  |

### 1.5 Secrets (`secrets.yaml`)

| Resource            | Type                             | Details                              |
|---------------------|----------------------------------|--------------------------------------|
| RDSPasswordSecret   | AWS::SecretsManager::Secret      | `/lenie/dev/rds/password`, user: lenie |

---

## 2. Database

### 2.1 RDS PostgreSQL (`rds.yaml`)

| Resource                  | Type                       | Details                                |
|---------------------------|----------------------------|----------------------------------------|
| MyDB                      | AWS::RDS::DBInstance       | PostgreSQL, db.t3.micro, 20 GB, single-AZ |
| DbSubnetGroup             | AWS::RDS::DBSubnetGroup    | 2 DB subnets                           |
| MyDatabaseSecurityGroup   | AWS::EC2::SecurityGroup    | Port 5432 ingress                      |

### 2.2 DynamoDB (`dynamodb-documents.yaml`)

| Resource              | Type                      | Details                                          |
|-----------------------|---------------------------|--------------------------------------------------|
| LenieDocumentsTable   | AWS::DynamoDB::Table      | `lenie_dev_documents`, PAY_PER_REQUEST, KMS encrypted |

- **Key Schema**: pk (HASH), sk (RANGE)
- **GSI**: `DateIndex` (created_date HASH, sk RANGE, projection: ALL)
- **PITR**: Disabled for DEV

---

## 3. Queues & Notifications

### 3.1 SQS Documents (`sqs-documents.yaml`)

| Resource            | Type                    | Details                                     |
|---------------------|-------------------------|---------------------------------------------|
| LenieDocumentsSQS   | AWS::SQS::Queue         | `lenie-dev-documents`, retention: 14 days   |
| SQSNameParameter    | AWS::SSM::Parameter     | Queue name                                  |
| SQSUrlParameter     | AWS::SSM::Parameter     | Queue URL                                   |

### 3.2 SQS Application Errors (`sqs-application-errors.yaml`)

| Resource                | Type                       | Details                                       |
|-------------------------|----------------------------|-----------------------------------------------|
| LenieDevProblemsDLQ     | AWS::SQS::Queue            | `lenie-dev-problems-dlq`, retention: 14 days  |
| LenieDevProblemsTopic   | AWS::SNS::Topic            | `lenie-dev-problems`                          |
| EmailSubscription       | AWS::SNS::Subscription     | Email → krzysztof@lenie-ai.eu                 |

---

## 4. Storage (S3)

### 4.1 Video Storage (`s3.yaml`)

| Resource      | Type                 | Details                          |
|---------------|----------------------|----------------------------------|
| MyS3Bucket    | AWS::S3::Bucket      | `lenie-dev-video-to-text`        |

### 4.2 CloudFormation Artifacts (`s3-cloudformation.yaml`)

| Resource                     | Type                    | Details                                   |
|------------------------------|-------------------------|-------------------------------------------|
| MyS3Bucket                   | AWS::S3::Bucket         | `lenie-2025-dev-cloudformation`           |
| CloudFormationSSMParameter   | AWS::SSM::Parameter     | `/lenie/dev/s3/cloudformation/name`       |

---

## 5. Compute - EC2

### 5.1 EC2 Instance (`ec2-lenie.yaml`)

| Resource                | Type                          | Details                                    |
|-------------------------|-------------------------------|--------------------------------------------|
| EC2Instance             | AWS::EC2::Instance            | t4g.micro (ARM64), Amazon Linux 2023       |
| InstanceSecurityGroup   | AWS::EC2::SecurityGroup       | SSH (22), HTTP (80), HTTPS (443)           |
| ElasticIP               | AWS::EC2::EIP                 | Static public IP                           |
| EIPAssociation          | AWS::EC2::EIPAssociation      | -                                          |
| InstanceRole            | AWS::IAM::Role                | AmazonSSMManagedInstanceCore               |
| InstanceProfile         | AWS::IAM::InstanceProfile     | -                                          |

### 5.2 Launch Template (`lenie-launch-template.yaml`)

| Resource                                    | Type                          | Details                    |
|---------------------------------------------|-------------------------------|----------------------------|
| ApplicationLaunchTemplate                   | AWS::EC2::LaunchTemplate      | Configurable instance type |
| ApplicationLaunchTemplateParam              | AWS::SSM::Parameter           | Template ID                |
| ApplicationLaunchTemplateLatestVersionParam | AWS::SSM::Parameter           | Latest version number      |

---

## 6. Compute - Lambda Functions

### 6.1 RDS Start (`lambda-rds-start.yaml`)

| Resource                 | Type                     | Details                                        |
|--------------------------|--------------------------|------------------------------------------------|
| RDSStartLambdaFunction   | AWS::Lambda::Function    | RDS start/stop, timeout: 60s                   |
| RDSStartLambdaRole       | AWS::IAM::Role           | rds:Start/Stop/Describe, ssm:GetParameter      |

### 6.2 URL Add to SQS (`lambda-weblink-put-into-sqs.yaml`)

| Resource            | Type                     | Details                            |
|---------------------|--------------------------|------------------------------------|
| MyLambdaFunction    | AWS::Lambda::Function    | Sends web links to SQS, timeout: 10s |

### 6.3 SQS to RDS (`sqs-to-rds-lambda.yaml`)

| Resource              | Type                     | Details                                           |
|-----------------------|--------------------------|---------------------------------------------------|
| MyLambdaFunction      | AWS::Lambda::Function    | `lenie-dev-sqs-to-rds-lambda`, timeout: 900s, VPC-attached |
| LambdaExecutionRole   | AWS::IAM::Role           | logs, sqs:Delete/Receive/GetQueueAttributes       |

- **Layers**: AWS Lambda Powertools, lenie_all_layer, psycopg2_new_layer
- **Environment**: AWS_QUEUE_URL_ADD, PostgreSQL connection vars

### 6.4 URL Add (`url-add.yaml`)

| Resource                       | Type                           | Details                                      |
|--------------------------------|--------------------------------|----------------------------------------------|
| LenineUrlAddLambdaFunction     | AWS::Lambda::Function          | `lenie-dev-url-add`, timeout: 30s            |
| LenineUrlAddLogGroup           | AWS::Logs::LogGroup            | Retention: 7 days                            |
| LambdaExecutionRole            | AWS::IAM::Role                 | logs, sqs:SendMessage, s3:Put/Get, dynamodb:Put/Update/BatchWrite |
| UrlAddApi                      | AWS::ApiGateway::RestApi       | -                                            |
| UrlAddResource                 | AWS::ApiGateway::Resource      | Path: /url_add                               |
| UrlAddMethod                   | AWS::ApiGateway::Method        | POST, API Key required                       |
| UrlAddOptionsMethod            | AWS::ApiGateway::Method        | OPTIONS (CORS)                               |
| ApiStage                       | AWS::ApiGateway::Stage         | Stage: v1                                    |
| ApiDeployment                  | AWS::ApiGateway::Deployment    | -                                            |
| LambdaApiPermission            | AWS::Lambda::Permission        | -                                            |

---

## 7. API Gateway - Application API (`api-gw-app.yaml`)

| Resource              | Type                        | Details                                          |
|-----------------------|-----------------------------|--------------------------------------------------|
| LambdaExecutionRole   | AWS::IAM::Role              | logs:*                                           |
| AppDBFunction         | AWS::Lambda::Function       | `lenie-dev-app-server-db`, timeout: 30s          |
| AppInternetFunction   | AWS::Lambda::Function       | `lenie-dev-app-server-internet`, timeout: 30s    |
| LenieApi              | AWS::ApiGateway::RestApi    | `lenie_dev_app`, REGIONAL                        |

**API Endpoints** (all secured with x-api-key):

| Path                              | Methods        | Description                    |
|-----------------------------------|----------------|--------------------------------|
| `/website_list`                   | GET, OPTIONS   | List documents                 |
| `/website_get`                    | GET, OPTIONS   | Get document by ID             |
| `/website_save`                   | POST, OPTIONS  | Save/update document           |
| `/website_delete`                 | GET, POST, OPTIONS | Delete document            |
| `/website_download_text_content`  | POST, OPTIONS  | Download webpage content       |
| `/website_split_for_embedding`    | POST, OPTIONS  | Split text for embeddings      |
| `/website_similar`                | POST, OPTIONS  | Find similar documents         |
| `/website_is_paid`                | POST, OPTIONS  | Check if content is paywalled  |
| `/website_get_next_to_correct`    | GET, OPTIONS   | Get next document to review    |
| `/url_add`                        | POST, OPTIONS  | Add new URL                    |
| `/ai_embedding_get`              | POST, OPTIONS  | Generate embeddings            |
| `/ai_ask`                         | POST, OPTIONS  | Ask AI a question              |

---

## 8. API Gateway - Infrastructure API (`api-gw-infra.yaml`)

| Resource              | Type                        | Details                                     |
|-----------------------|-----------------------------|---------------------------------------------|
| LambdaExecutionRole   | AWS::IAM::Role              | logs:*                                      |
| SqsSizeFunction       | AWS::Lambda::Function       | `lenie-dev-sqs-size`, timeout: 30s          |
| RdsStartFunction      | AWS::Lambda::Function       | `lenie-dev-rds-start`                       |
| RdsStopFunction       | AWS::Lambda::Function       | `lenie-dev-rds-stop`                        |
| RdsStatusFunction     | AWS::Lambda::Function       | `lenie-dev-rds-status`                      |
| Ec2StatusFunction     | AWS::Lambda::Function       | `lenie-dev-ec2-status`                      |
| Ec2StatusStart        | AWS::Lambda::Function       | `lenie-dev-ec2-start`                       |
| Ec2StatusStop         | AWS::Lambda::Function       | `lenie-dev-ec2-stop`                        |
| LenieApi              | AWS::ApiGateway::RestApi    | `lenie_dev_infra`, REGIONAL                 |
| ApiStage              | AWS::ApiGateway::Stage      | Stage: v1                                   |
| ApiDeployment         | AWS::ApiGateway::Deployment | -                                           |

**API Endpoints** (all secured with x-api-key):

| Path                  | Methods        | Description           |
|-----------------------|----------------|-----------------------|
| `/sqs/size`           | POST, OPTIONS  | Get SQS queue size    |
| `/database/start`     | POST, OPTIONS  | Start RDS instance    |
| `/database/stop`      | POST, OPTIONS  | Stop RDS instance     |
| `/database/status`    | POST, OPTIONS  | Get RDS status        |
| `/vpn-server/start`   | POST, OPTIONS  | Start EC2 (VPN)       |
| `/vpn-server/stop`    | POST, OPTIONS  | Stop EC2 (VPN)        |
| `/vpn-server/status`  | POST, OPTIONS  | Get EC2 status        |

---

## 9. API Gateway - Chrome Extension (`api-gw-url-add.yaml`)

| Resource               | Type                           | Details                                        |
|------------------------|--------------------------------|------------------------------------------------|
| LenieApiGateway        | AWS::ApiGateway::RestApi       | `lenie_dev_add_from_chrome_extension`, REGIONAL |
| LenieApiDeployment     | AWS::ApiGateway::Deployment    | -                                              |
| LenieApiKey            | AWS::ApiGateway::ApiKey        | `lenie-dev-api-key`                            |
| LenieUsagePlan         | AWS::ApiGateway::UsagePlan     | Rate: 1000/s, Burst: 2000, Quota: 10000/month |
| LenieUsagePlanKey      | AWS::ApiGateway::UsagePlanKey  | -                                              |
| LambdaInvokePermission | AWS::Lambda::Permission        | -                                              |

**API Endpoint**: `/url_add` (POST, OPTIONS) - secured with API Key

---

## 10. Orchestration - Step Functions (`sqs-to-rds-step-function.yaml`)

| Resource                  | Type                                  | Details                                    |
|---------------------------|---------------------------------------|--------------------------------------------|
| MyStateMachine            | AWS::StepFunctions::StateMachine      | `lenie-dev-sqs-to-rds`                     |
| StateMachineRole          | AWS::IAM::Role                        | sqs, rds, lambda:Invoke, logs              |
| StateMachineLogGroup      | AWS::Logs::LogGroup                   | Retention: 14 days                         |
| StepFunctionInvokerRole   | AWS::IAM::Role                        | states:StartExecution                      |
| EventBridgeScheduler      | AWS::Scheduler::Schedule              | Cron-based trigger (parameter-driven)      |

**Workflow Steps**:
1. Check SQS message count
2. Check RDS status (available / stopped / starting / stopping)
3. Start RDS if needed, wait for availability
4. Process messages in batch (Map: receive → Lambda invoke → delete from SQS)
5. Loop until queue is empty
6. Optionally stop RDS when done

---

## 11. Email - SES (`ses.yaml`)

| Resource              | Type                        | Details                                   |
|-----------------------|-----------------------------|-------------------------------------------|
| SESDomainIdentity     | AWS::SES::EmailIdentity     | `dev.lenie-ai.eu`, DKIM: RSA_2048_BIT    |
| LambdaExecutionRole   | AWS::IAM::Role              | route53:*, ses:GetIdentityDkimAttributes  |
| DnsUpdaterFunction    | AWS::Lambda::Function       | Auto-updates Route53 DKIM records, python3.13 |
| DnsUpdateTrigger      | Custom::DnsUpdater          | Triggers DNS update on stack changes      |

---

## 12. Organization & Governance

### 12.1 Organization (`organization.yaml`)

| Resource          | Type                                  | Details             |
|-------------------|---------------------------------------|---------------------|
| MyOrganization    | AWS::Organizations::Organization      | FeatureSet: ALL     |

### 12.2 Identity Store (`identityStore.yaml`)

| Resource                      | Type                                       | Details                  |
|-------------------------------|--------------------------------------------|--------------------------|
| LenieAIDevelopersGroup        | AWS::IdentityStore::Group                  | "Lenie-Developers"       |
| ZiutusInDevelopersGroup       | AWS::IdentityStore::GroupMembership        | User → Developers group  |

### 12.3 Service Control Policies

**Block All (`scp-block-all.yaml`)**

| Resource              | Type                            | Details                   |
|-----------------------|---------------------------------|---------------------------|
| BlackAllScpPolicy     | AWS::Organizations::Policy      | Deny *, for sandbox accounts |

**Block SSO Creation (`scp-block-sso-creation.yaml`)**

| Resource              | Type                            | Details                       |
|-----------------------|---------------------------------|-------------------------------|
| BlackAllScpPolicy     | AWS::Organizations::Policy      | Deny sso:CreateInstance       |

**Region Restriction (`scp-only-allowed-reginos.yaml`)**

| Resource                    | Type                            | Details                                         |
|-----------------------------|---------------------------------|-------------------------------------------------|
| DenyOutsideIrelandPolicy   | AWS::Organizations::Policy      | Allowed: eu-west-1, eu-west-2, eu-central-1, us-east-1 |

---

## 13. Monitoring & Budgets (`budget.yaml`)

| Resource          | Type                      | Details                              |
|-------------------|---------------------------|--------------------------------------|
| AccountBudget     | AWS::Budgets::Budget      | $20/month, COST type                 |

**Alert Thresholds**:
- Actual spend > 50% → email notification
- Actual spend > 80% → email notification
- Forecasted spend > 100% → email notification

---

## Architecture Diagram (Logical)

```
                    ┌─────────────────────────────────────┐
                    │          API Gateway (x3)            │
                    │  app / infra / chrome-extension      │
                    └──────────┬──────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
     ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
     │   Lambda     │  │   Lambda     │  │   Lambda     │
     │ app-server-db│  │ app-internet │  │  url-add     │
     └──────┬──────┘  └──────────────┘  └──────┬───────┘
            │                                   │
            ▼                                   ▼
     ┌──────────────┐                   ┌──────────────┐
     │  RDS         │                   │  SQS         │
     │  PostgreSQL  │                   │  documents   │
     └──────────────┘                   └──────┬───────┘
                                               │
                                        ┌──────▼───────┐
                                        │ Step Function │
                                        │ sqs-to-rds   │
                                        └──────┬───────┘
                                               │
                                        ┌──────▼───────┐
                                        │   Lambda     │
                                        │ sqs-to-rds   │
                                        └──────┬───────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │  RDS         │
                                        │  PostgreSQL  │
                                        └──────────────┘

     ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
     │  S3          │    │  DynamoDB    │    │  EC2         │
     │  video/cf    │    │  documents   │    │  t4g.micro   │
     └──────────────┘    └──────────────┘    └──────────────┘
```

---

## Parameter Files (DEV)

All DEV parameter files are in `cloudformation/parameters/dev/`:

| File                           | Key Parameters                                       |
|--------------------------------|------------------------------------------------------|
| api-gw-app.json                | ProjectCode: lenie, stage: dev                       |
| api-gw-infra.json              | ProjectCode: lenie, stage: dev, OpenvpnEC2Name       |
| api-gw-url-add.json            | stage: dev, LambdaFunctionName: lenie-dev-url-add    |
| budget.json                    | BudgetAmount: 20, AlertEmail                         |
| dynamodb-documents.json        | ProjectCode: lenie, Environment: dev                 |
| ec2-lenie.json                 | ProjectName, Environment, SshKeyName                 |
| env-setup.json                 | stage: dev                                           |
| lenie-launch-template.json     | ImageId, InstanceType                                |
| rds.json                       | RDSPasswordSecretArn, VPCId (SSM), Subnets (SSM)    |
| s3-cloudformation.json         | ProjectName: lenie, Environment: dev                 |
| secrets.json                   | Environment: dev, DBMasterUserPassword               |
| sqs-application-errors.json    | ProjectName: lenie, Environment: dev                 |
| sqs-documents.json             | ProjectName: lenie, Environment: dev                 |
| sqs-to-rds-lambda.json         | ProjectName: lenie, Environment: dev                 |
| sqs-to-rds-step-function.json  | ScheduleExpression (cron)                            |
| url-add.json                   | ProjectCode: lenie, Environment: dev                 |
| vpc.json                       | VpcName: lenie-dev                                   |

---

## 14. Serverless Lambda Functions (`serverless/`)

Source code for all 11 Lambda functions deployed via CloudFormation, plus 3 shared Lambda layers.

### Directory Structure

```
serverless/
├── lambdas/
│   ├── app-server-db/           # Application - DB operations
│   ├── app-server-internet/     # Application - internet/AI operations
│   ├── ec2-start/               # EC2 instance start
│   ├── ec2-status/              # EC2 instance status
│   ├── ec2-stop/                # EC2 instance stop
│   ├── rds-start/               # RDS instance start
│   ├── rds-status/              # RDS instance status
│   ├── rds-stop/                # RDS instance stop
│   ├── sqs-into-rds/            # SQS → PostgreSQL processor
│   ├── sqs-size/                # SQS queue message count
│   ├── sqs-weblink-put-into/    # URL ingestion → S3 + DynamoDB + SQS
│   └── tmp/                     # Empty placeholder
├── lambda_layers/               # Shared dependency layers
├── env.sh / env_lenie_2025.sh   # Environment config
├── zip_to_s3.sh                 # Package & deploy to S3
└── create_empty_lambdas.sh      # Create placeholder functions
```

### Function Overview

| Function | Category | AWS Services | Env Vars | Uses backend/library |
|---|---|---|---|---|
| app-server-db | Application | RDS/PostgreSQL | OpenAI, EMBEDDING_MODEL, DB vars | Yes |
| app-server-internet | Application | External APIs | OpenAI, EMBEDDING_MODEL | Yes |
| sqs-weblink-put-into | Document Processing | S3, DynamoDB, SQS | AWS_QUEUE_URL_ADD, BUCKET_NAME, DYNAMODB_TABLE_NAME | No |
| sqs-into-rds | Document Processing | RDS, SQS | PostgreSQL vars | Yes |
| rds-start | Infrastructure | RDS | DB_ID | No |
| rds-stop | Infrastructure | RDS | DB_ID | No |
| rds-status | Infrastructure | RDS | DB_ID | No |
| ec2-start | Infrastructure | EC2 | INSTANCE_ID | No |
| ec2-stop | Infrastructure | EC2 | INSTANCE_ID | No |
| ec2-status | Infrastructure | EC2 | INSTANCE_ID | No |
| sqs-size | Infrastructure | SQS, SSM | AWS_REGION | No |

### 14.1 Application Functions

#### app-server-db

Main application Lambda handling all database operations. Routes requests by API Gateway path.

**Endpoints:**

| Path | Method | Description |
|---|---|---|
| `/website_list` | POST | List documents (filters: document_state, type, search_in_document) |
| `/website_get` | GET | Get document by ID |
| `/website_save` | POST | Create/update document (url, type, state, text, title, language, summary, tags, source, author, note) |
| `/website_delete` | GET | Delete document by ID |
| `/website_is_paid` | POST | Check if URL has paywall |
| `/website_get_next_to_correct` | GET | Get next document to review (by id, type, state) |
| `/website_similar` | POST | Vector similarity search (embedds[], model, limit) |
| `/website_split_for_embedding` | POST | Split text for embedding (text, chapter_list) |

**Dependencies:** StalkerWebDocumentDB, WebsitesDBPostgreSQL, split_text_for_embedding, chapters_text_to_list, website_is_paid

#### app-server-internet

Internet-facing Lambda for web scraping, AI/LLM operations, embeddings, and translations.

**Endpoints:**

| Path | Method | Description |
|---|---|---|
| `/translate` | POST | Translate text (text, target_language, source_language) |
| `/website_download_text_content` | POST | Download & parse webpage (url) → text, title, summary, language |
| `/ai_embedding_get` | POST | Generate vector embeddings (model, text) |
| `/ai_ask` | POST | Query LLM with context (text, query, model) |

**Dependencies:** library.ai, text_translate, download_raw_html, webpage_raw_parse, get_embedding

### 14.2 Document Processing Functions

#### sqs-weblink-put-into

URL ingestion function. Receives URLs via API Gateway, stores content in S3, metadata in DynamoDB, and queues for async processing in SQS.

**Input (JSON):**
- `url` (required), `type` (required), `text`, `html`, `title`, `language`, `note`, `source` (default: "own"), `paywall`, `ai_summary`, `ai_correction`, `chapter_list`

**Flow:** Validate → Generate UUID → Upload text/HTML to S3 → Save metadata to DynamoDB (PK=DOCUMENT, SK=timestamp#uuid) → Send SQS message (10s delay)

#### sqs-into-rds

SQS event-triggered function. Reads messages from SQS queue and persists documents to PostgreSQL via `StalkerWebDocumentDB`.

**Flow:** Parse SQS message → Check if URL exists in DB → Map fields to document object → `web_doc.save()` → Return ReceiptHandle

### 14.3 Infrastructure Management Functions

#### rds-start / rds-stop / rds-status

RDS instance lifecycle management. Each uses `DB_ID` env var to identify the target instance.
- **rds-start**: `rds.start_db_instance()`
- **rds-stop**: `rds.stop_db_instance()`
- **rds-status**: `rds.describe_db_instances()` → returns `DBInstanceStatus`

#### ec2-start / ec2-stop / ec2-status

EC2 instance lifecycle management. Each uses `INSTANCE_ID` env var.
- **ec2-start**: `ec2.start_instances()`
- **ec2-stop**: `ec2.stop_instances()`
- **ec2-status**: `ec2.describe_instances()` → returns `State['Name']`

#### sqs-size

Returns approximate message count in SQS queue. Reads queue URL from SSM Parameter Store (`/lenie/dev/sqs_queue/new_links`), then queries `ApproximateNumberOfMessages` attribute.

### 14.4 Lambda Layers

| Layer | Packages | Used By |
|---|---|---|
| psycopg2_new_layer | psycopg2-binary 2.9.10 | sqs-into-rds, app-server-db |
| lenie_all_layer | pytube, urllib3, requests, beautifulsoup4 | app-server-db, app-server-internet |
| lenie_openai | openai SDK | app-server-internet |

All layers built with `manylinux2014_x86_64` platform for Lambda compatibility.

---

## 15. Resources Without CloudFormation Templates

The following AWS resources related to Project Lenie exist in the account (us-east-1) but are **not managed by any CloudFormation template**. They were created manually, via scripts, or through other tools.

### 15.1 S3 Buckets

| Bucket | Purpose | Notes |
|--------|---------|-------|
| `lenie-ai-logs` | Centralized logging | |
| `lenie-dev-app-web` | React frontend static files | CloudFront origin for `app.dev.lenie-ai.eu` |
| `lenie-dev-emails` | Email storage | |
| `lenie-dev-excel-reports` | Excel report files | |
| `lenie-dev-helm` | Helm chart hosting (DEV) | CloudFront origin for `helm.dev.lenie-ai.eu` |
| `lenie-dev-web` | Web content | |
| `lenie-gitlab-test` | GitLab CI testing | Candidate for cleanup |
| `lenie-s3-tmp` | Temporary storage | Candidate for cleanup |
| `lenie-s3-web-test` | Web test | CloudFront origin, candidate for cleanup |
| `lenie-prod-video-to-text` | Video transcriptions (PROD) | |

### 15.2 CloudFront Distributions

| ID | Domain Alias | S3 Origin | Notes |
|----|-------------|-----------|-------|
| `ETIQTXICZBECA` | `app.dev.lenie-ai.eu` | lenie-dev-app-web | DEV frontend |
| `E2ZLSEEB8OVYOM` | `helm.dev.lenie-ai.eu` | lenie-dev-helm | DEV Helm charts |
| `E19SWSRXVWFGJQ` | *(none)* | lenie-s3-web-test | Test distribution, candidate for cleanup |

### 15.3 Lambda Functions

**Operational / infrastructure tools:**

| Function | Purpose |
|----------|---------|
| `rds-start-reporter-sns` | SNS notification on RDS start |
| `ses_s3_send_email` | Send emails via SES with S3 content |
| `git-webhooks` | Handle Git webhook events |
| `auditor_review_ec2` | EC2 audit review |

**AMI management pipeline (archived — VM-based distribution approach shelved):**

| Function | Purpose | Notes |
|----------|---------|-------|
| `createImageLambda` | Create AMI from tagged EC2 instance | Archived: see `serverless/CLAUDE.md` |
| `getImageStateLambda` | Check AMI creation status | Archived: see `serverless/CLAUDE.md` |
| `copyImageLambda` | Copy AMI to DR region (encrypted) | Archived: see `serverless/CLAUDE.md` |
| `setSsmParamLambda` | Store AMI ID in SSM Parameter Store | Archived: see `serverless/CLAUDE.md` |

These 4 functions formed a pipeline for backing up EC2 instances running Lenie as a Linux VM connecting to the database. This distribution approach has been shelved in favor of containerized (Docker/K8s) and serverless (Lambda) deployments.

**Legacy / candidates for cleanup:**

| Function | Purpose | Notes |
|----------|---------|-------|
| `infra-allow-ip-in-secrutity-group` | Add caller IP to Security Group (RDP 3389) | Archived: code downloaded from AWS, see `serverless/CLAUDE.md` |
| `lenie_2_internet_tmp` | Temp version of app-server-internet | Should be removed |
| `lenie-url-add` | Older version of url-add | Replaced by `lenie-dev-url-add` (CF-managed) |
| `lenie_ses_excel_summary` | Generate and send Excel summary via SES | Archived: code downloaded from AWS, see `serverless/CLAUDE.md` |
| `jenkins-start-job` | Start Jenkins jobs | Archived: code downloaded from AWS, see `serverless/CLAUDE.md` |
| `step-function-test` | Step Functions testing | Test artifact |

### 15.4 DynamoDB Tables

| Table | Purpose | Notes |
|-------|---------|-------|
| `lenie_cache_ai_query` | Cache for AI/LLM query results | PAY_PER_REQUEST |
| `lenie_cache_language` | Cache for language detection results | PAY_PER_REQUEST |
| `lenie_cache_translation` | Cache for translation results | PAY_PER_REQUEST |

### 15.5 SQS Queues

| Queue | Purpose |
|-------|---------|
| `lenie-dev-sqs-to-rds-dlq` | Dead Letter Queue for sqs-to-rds processing |
| `rds-monitor-sqs` | RDS monitoring events |

### 15.6 SNS Topics

| Topic | Purpose |
|-------|---------|
| `rds-monitor-sns` | RDS monitoring notifications |
| `ses-monitoring` | SES delivery/bounce monitoring |

### 15.7 API Gateway

| API ID | Name | Notes |
|--------|------|-------|
| `1bkc3kz7c9` | `lenie_split` | Undocumented, candidate for review |
| `pir31ejsf2` | `lenie_chrome_extension` | Older version, replaced by CF-managed `lenie_dev_add_from_chrome_extension` |

### 15.8 Step Functions

| State Machine | Purpose | Notes |
|---------------|---------|-------|
| `jenkins-start-run-job` | Jenkins job orchestration | Archived: definition downloaded from AWS, see `serverless/CLAUDE.md` |

### 15.9 SES Email Identities

| Identity | Notes |
|----------|-------|
| `lenie-ai.eu` | Root domain (CF template `ses.yaml` covers only `dev.lenie-ai.eu`) |
| `krzysztof@itsnap.eu` | Personal email identity |

### 15.10 Lambda Layers

| Layer | Packages | Notes |
|-------|----------|-------|
| `lenie_all_layer` | pytube, urllib3, requests, beautifulsoup4 | Deployed via `zip_to_s3.sh` |
| `lenie_openai` | openai SDK | Deployed via `zip_to_s3.sh` |
| `psycopg2_new_layer` | psycopg2-binary 2.9.10 | Deployed via `zip_to_s3.sh` |

### 15.11 Budget (Discrepancy)

| Actual | Documented (budget.yaml) |
|--------|--------------------------|
| "My Monthly Cost Budget", $8/month | "AccountBudget", $20/month |

The deployed budget differs from the template — either the template was not used for deployment, or the budget was manually modified.

### 15.12 Summary

| Resource Type | Without CF Template | With CF Template |
|---------------|--------------------:|:----------------:|
| S3 Buckets | 10 | 3 |
| CloudFront Distributions | 3 | 1 |
| Lambda Functions | 14 | 11 |
| DynamoDB Tables | 3 | 1 |
| SQS Queues | 2 | 2 |
| SNS Topics | 2 | 1 |
| API Gateway | 2 | 3 |
| Step Functions | 1 | 1 |
| SES Identities | 2 | 1 |
| Lambda Layers | 3 | 0 |
| **Total** | **~42** | **~24** |
