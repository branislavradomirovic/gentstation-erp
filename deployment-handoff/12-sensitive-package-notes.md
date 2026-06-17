# 12. Sensitive Package Notes

This repository must not include real production secrets or live customer data.

Allowed sanitized handoff artifacts:

- `deploy/env/.env.production.example`
- `deploy/docker-compose.prod.yml`
- `deploy/scripts/healthcheck.sh`
- `deploy/scripts/healthcheck_web.sh`
- `deploy/scripts/healthcheck_worker.sh`
- `vm/.env.vm.example`
- `vm/.env.production.example`
- `vm/docker-compose.vm.yml`
- documentation files in this folder

Current status of the one-folder handoff archive:

- VM deployment instructions: included
- VM Docker Compose stack: included
- Sanitized production env template: included
- Real environment file with secrets: not included
- PostgreSQL dump: not included

Important packaging note:

- create a local untracked `.env` on the target server from one of the sanitized examples
- fill real secrets only on the target server or in an approved secret manager
- do not email or commit live `.env` files or database dumps

Database transfer guidance:

- generate fresh dumps outside the repository when a real migration is needed
- share dumps only through an approved internal channel
- keep backup retention and restore testing in the production operations plan, not in git

This handoff folder now contains the core items needed for a production handoff,
with the `deploy/` bundle as the default path:

- Ubuntu production deployment documentation
- Docker Compose stack for the production bundle
- sanitized production environment examples

Recommended next step:

- share the repository plus server-only secret values through approved operational channels, keeping secrets and dumps out of version control.
