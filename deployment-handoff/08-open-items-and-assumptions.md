# 08. Open Items And Assumptions

## Assumptions captured in this handoff

1. AWS is the target platform.
2. The external team will deploy containers rather than run the app directly on a VM.
3. Amazon ECS Fargate is the preferred execution model.
4. PostgreSQL and Redis will be deployed as managed AWS services.
5. The current repository `Dockerfile` is the base production image.
6. Worker processes will run as separate services rather than being spawned from the web container.

## Important open decisions for the external team

### 1. Ollama hosting model

The application expects an Ollama endpoint through `OLLAMA_BASE_URL`.

The team must decide one of these:

- deploy Ollama separately in AWS
- point to an existing hosted Ollama-compatible endpoint
- disable or defer AI-dependent workflows for the first release

### 2. SMTP provider

The application supports SMTP-based email delivery. The team must confirm:

- which SMTP provider will be used
- what credentials will be supplied
- whether outbound SMTP from the chosen network path is allowed

### 3. Telegram enablement

The team must confirm whether Telegram is in scope for the first release. If not, the Telegram worker may be omitted from the initial deployment.

### 4. Persistent file storage

The current application image creates local `uploads` and `downloads` directories. This handoff does not assume durable shared storage.

The team should confirm:

- whether any uploaded/generated files must persist across deployments
- whether S3 or EFS is needed

### 5. Schema migration strategy

The current code still uses startup schema initialization behavior from the application.

This is acceptable for an initial handoff, but the long-term recommendation is:

- formalize migrations with Alembic
- make deployment-time migrations explicit and controlled

### 6. Authentication and hardening review

This handoff covers deployment, not a full production-readiness security assessment.

Before broader production rollout, consider:

- secret rotation policy
- password reset hardening
- audit/log retention policy
- backup and disaster recovery requirements
- least-privilege review for AWS IAM and database accounts

## Recommendation to application owner

When sharing this package with the external team, also provide:

- the exact repository URL
- the release tag or commit SHA to deploy
- who owns application-level decisions
- who owns infrastructure-level decisions
- a contact for secrets delivery
