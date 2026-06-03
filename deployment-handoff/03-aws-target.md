# 03. AWS Target Architecture

## Recommended target

Deploy on AWS using:

- Amazon ECR for container images
- Amazon ECS Fargate for runtime
- Amazon RDS PostgreSQL for database
- Amazon ElastiCache Redis for Redis
- AWS Secrets Manager for secrets
- Amazon CloudWatch Logs for logs
- Application Load Balancer for inbound web traffic
- Route 53 and ACM if DNS and TLS are managed in AWS

## Why this target is recommended

- The application is already container-ready.
- The app has multiple long-running service roles.
- Fargate removes EC2 patching and host maintenance.
- RDS and ElastiCache reduce operational burden for the external team.
- This model maps cleanly to the current repository structure.

## ECS service layout

Create one ECS task definition family per logical service or one shared image with separate ECS services using different commands.

Recommended services:

1. `gentstationai-web`
2. `gentstationai-ai-worker`
3. `gentstationai-telegram-worker`
4. `gentstationai-report-scheduler`

## Image strategy

Recommended:

- build one image from the repository `Dockerfile`
- push to ECR
- reuse the same image for all services
- override the command per ECS service where needed

Commands:

- web:
  `python -m streamlit run app.py --server.port=8501 --server.address=0.0.0.0`
- ai worker:
  `python -m core.ai_worker`
- telegram worker:
  `python -m core.bot_worker`
- report scheduler:
  `python -m core.report_scheduler`

## Suggested AWS networking

- Place ECS services, RDS, and Redis in private subnets where possible.
- Expose only the ALB publicly.
- Restrict RDS and Redis security groups to ECS task security groups.
- Permit outbound internet access from ECS tasks for:
  - Python package startup is not needed at runtime
  - Telegram API access
  - SMTP access
  - Ollama access if external

## Suggested sizing for initial deployment

These are starting points only.

### Web

- 1-2 tasks
- 0.5 to 1 vCPU
- 1-2 GB RAM

### AI worker

- 1 task
- 1-2 vCPU
- 2-4 GB RAM

### Telegram worker

- 1 task
- 0.25-0.5 vCPU
- 0.5-1 GB RAM

### Report scheduler

- 1 task
- 0.25-0.5 vCPU
- 0.5-1 GB RAM

Final sizing should be validated against real workload.

## Health checks

The Docker image exposes a Streamlit health endpoint:

```text
/_stcore/health
```

Recommended ALB health check for the web service:

- protocol: HTTP
- port: traffic port
- path: `/_stcore/health`
- success codes: `200`

Worker services do not expose HTTP endpoints and should be monitored via:

- container health if the team adds checks
- ECS task state
- CloudWatch logs

## Persistence notes

- Database data must be persisted in RDS.
- Redis should be treated as managed runtime state, not as a primary system of record.
- Local container directories like `uploads` and `downloads` are created in the image, but should not be treated as durable storage unless the team explicitly introduces shared storage such as S3 or EFS.

## Recommended DNS/TLS

- Terminate TLS at the ALB using ACM certificates.
- Put a friendly DNS record in front of the ALB.
- Set `APP_LOGIN_URL` to the externally reachable HTTPS application URL.
