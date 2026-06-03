# 04. Deployment Procedure

## Objective

This procedure describes the recommended first AWS deployment of GentStationAI.

## Pre-deployment inputs required

The deployment team should receive:

- source repository access or a source bundle
- the `Dockerfile`
- the list of required environment variables
- production secrets
- the desired DNS name
- confirmation whether AI features are in scope for the first release
- confirmation whether Telegram integration is in scope for the first release
- confirmation whether SMTP email functionality is in scope for the first release

## Deployment sequence

### Step 1. Build and publish the container image

Build from the repository root using the provided `Dockerfile`.

Expected image contents:

- Python 3.11 application
- all Python dependencies from `requirements.txt`
- Streamlit app
- worker code

Push the built image to Amazon ECR.

### Step 2. Provision managed data services

Provision:

- one Amazon RDS PostgreSQL instance or cluster
- one Amazon ElastiCache Redis instance

For PostgreSQL:

- create a database for the application
- create a least-privilege application user with required schema permissions
- ensure network access from ECS tasks

For Redis:

- create a reachable Redis endpoint
- ensure network access from ECS tasks

### Step 3. Store application secrets

Store secrets in AWS Secrets Manager or SSM Parameter Store.

At minimum the deployment team should prepare:

- `DATABASE_URL`
- `REDIS_URL`
- `INITIAL_ADMIN_PASSWORD`
- `TELEGRAM_BOT_TOKEN` if Telegram is enabled
- SMTP credentials if email is enabled

### Step 4. Deploy the web service

Deploy one ECS Fargate service for the web app using the shared image.

Recommended environment flags:

```text
APP_ENV=production
RUN_SCHEMA_MIGRATIONS_ON_STARTUP=1
STRICT_SCHEMA_INIT=1
AUTO_START_BACKGROUND_WORKERS=0
AUTO_START_AI_WORKER=0
AUTO_START_TELEGRAM_BOT=0
AUTO_START_REPORT_SCHEDULER=0
```

Attach the service to an Application Load Balancer.

Configure the health check path:

```text
/_stcore/health
```

### Step 5. Deploy worker services

Deploy separate ECS Fargate services using the same image with different commands.

Worker environment guidance:

```text
APP_ENV=production
SKIP_SCHEMA_INIT=1
```

Deploy:

- AI worker
- Telegram worker if Telegram is enabled
- Report scheduler

### Step 6. Configure outbound integrations

If used, validate:

- SMTP connectivity
- Telegram API access
- Ollama API access

Important:

- If `OLLAMA_BASE_URL` points to an internal or self-hosted endpoint, confirm AWS network routing and security group access.
- If the external team does not deploy Ollama, they must point `OLLAMA_BASE_URL` to an existing reachable service or disable AI-dependent workflows by agreement.

### Step 7. Initialize schema and first admin access

The application currently relies on startup schema initialization behavior.

Observed configuration:

- web service should run schema initialization
- workers should skip schema initialization

Recommended first deployment behavior:

1. start database and Redis
2. deploy only the web service first
3. wait for successful startup and schema initialization
4. validate web login page load
5. deploy workers after web startup succeeds

Admin bootstrap inputs:

- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `INITIAL_ADMIN_EMAIL`

### Step 8. Perform smoke testing

Run the checklist in `07-smoke-test-checklist.md`.

### Step 9. Enable monitoring and log retention

Before go-live, ensure:

- CloudWatch logs are enabled for every ECS service
- log retention is configured
- alarms exist for repeated task failures
- alarms exist for unhealthy web targets
- alarms exist for RDS connectivity problems if possible

## Rollback guidance

If the first deployment fails:

1. inspect CloudWatch logs for the failed service
2. verify secrets are correctly mounted or injected
3. verify `DATABASE_URL` and Redis reachability
4. verify security groups and subnet routing
5. disable worker rollout until the web service is healthy

If schema initialization fails, keep workers stopped until the database issue is resolved.
