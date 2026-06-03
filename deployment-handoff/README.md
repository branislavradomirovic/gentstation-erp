# GentStationAI Deployment Handoff

This folder is the handoff package for the external infrastructure team that will deploy GentStationAI on AWS.

The application is a containerized Python/Streamlit platform with supporting worker processes and managed stateful services.

This package now includes two deployment paths:

- AWS managed services path using ECS/RDS/ElastiCache
- single-VM path using Docker Compose, intended as the easiest way to recreate the environment in the cloud

Read the documents in this order:

1. `01-overview.md`
2. `02-architecture.md`
3. `03-aws-target.md`
4. `04-deployment-procedure.md`
5. `05-environment-and-secrets.md`
6. `06-operations-runbook.md`
7. `07-smoke-test-checklist.md`
8. `08-open-items-and-assumptions.md`
9. `09-vm-deployment.md`
10. `10-data-transfer-and-db-restore.md`
11. `11-owner-delivery-checklist.md`
12. `vm/docker-compose.vm.yml`
13. `vm/.env.vm.example`

Repository artifacts referenced by this handoff:

- `Dockerfile`
- `.env.example`
- `README.md`
- `render.yaml`
- `init_db.sql`

High-level deployment summary:

- Deploy the web app as a containerized service.
- Deploy background workers as separate containerized services.
- Use managed PostgreSQL and managed Redis.
- Store secrets in AWS Secrets Manager or SSM Parameter Store.
- Front the web service with an Application Load Balancer.

Recommended AWS service mapping:

- Amazon ECS Fargate
- Amazon ECR
- Amazon RDS for PostgreSQL
- Amazon ElastiCache for Redis
- AWS Secrets Manager
- Amazon CloudWatch Logs
- AWS Application Load Balancer

This package is intended to be sufficient for an initial AWS deployment handoff without requiring the deployment team to reverse-engineer the application.

For the easiest cloud recreation, start with the single-VM path in `09-vm-deployment.md`.
