# 06. Operations Runbook

## Daily operational view

The external team should treat GentStationAI as a small multi-service application platform.

The operational units are:

- web service
- ai worker
- telegram worker
- report scheduler
- postgres
- redis
- optional external services: SMTP, Telegram API, Ollama

## First things to check when something is wrong

1. Is the web service healthy behind the load balancer?
2. Can the web container connect to PostgreSQL?
3. Can the workers connect to PostgreSQL and Redis?
4. Are required secrets present?
5. Are external integrations reachable?

## Common failure patterns

### Web app fails to start

Likely causes:

- invalid or missing `DATABASE_URL`
- database not reachable from ECS
- schema initialization failure
- missing required environment variables

What to inspect:

- ECS task logs for the web service
- RDS connectivity and security groups
- startup environment values

### Workers restart repeatedly

Likely causes:

- missing `REDIS_URL`
- missing `TELEGRAM_BOT_TOKEN` for telegram worker
- unreachable `OLLAMA_BASE_URL` for AI worker
- database connectivity problems

What to inspect:

- ECS task logs for the affected worker
- presence of secrets
- security group rules
- DNS/routing to external services

### Application loads but features fail

Likely causes:

- SMTP integration not configured
- Telegram not configured
- Ollama not reachable
- schema partially initialized or outdated

What to inspect:

- app logs
- worker logs
- current environment variables
- database schema readiness

## Logging guidance

Enable CloudWatch logs for all services with clear log group names such as:

- `/gentstationai/web`
- `/gentstationai/ai-worker`
- `/gentstationai/telegram-worker`
- `/gentstationai/report-scheduler`

Set a retention policy based on organizational requirements.

## Monitoring guidance

Recommended alarms:

- ALB target health unhealthy
- ECS service task count below desired count
- repeated ECS task restarts
- RDS CPU or storage alarms
- Redis memory pressure alarms

## Deployment discipline

Recommended deployment order:

1. web service
2. ai worker
3. telegram worker
4. report scheduler

If the web service is unhealthy, do not continue rolling out workers.

## Backup and recovery expectations

The external team should implement:

- automated RDS backups
- retention policy aligned with business expectations
- restore procedure validation

Redis recovery can usually focus on service restoration rather than durable state restoration, unless the team later decides Redis contents are operationally critical.

## Security expectations

- keep secrets out of source control
- use private networking for RDS and Redis
- restrict access using security groups
- use HTTPS publicly through the ALB
- apply least privilege to task roles and database users

## Release management recommendation

The application owner should provide the external team with:

- a tagged application version
- a change summary
- known migration or configuration changes

The external team should avoid deploying directly from an unpinned branch without a release tag or commit SHA.
