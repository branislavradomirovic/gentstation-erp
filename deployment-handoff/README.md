# GentStationAI Deployment Handoff

This folder contains deployment notes for GentStationAI.

The dedicated Ubuntu production bundle in `deploy/` is now the canonical
production path. The older VM handoff materials in `deployment-handoff/vm/`
remain as legacy/reference notes.

The application is a containerized Python/Streamlit platform with supporting worker processes and stateful services.

Primary target:

- Ubuntu 22.04 or 24.04
- Docker Engine + Docker Compose plugin
- separate `web`, `ai-worker`, `telegram-worker`, and `report-scheduler` services
- PostgreSQL, Redis, reverse proxy, backups, and optional local Ollama
- `deploy/docker-compose.prod.yml` as the production entry point

Read the documents in this order:

1. `vm/README.md`
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
14. `vm/.env.production.example`
15. `12-sensitive-package-notes.md`

Repository artifacts referenced by this handoff:

- `Dockerfile`
- `.env.example`
- `README.md`
- `init_db.sql`

High-level deployment summary:

- Deploy the web app as a containerized service.
- Deploy background workers as separate containerized services.
- Use PostgreSQL and Redis alongside the app services.
- Keep secrets outside git and fill them only on the target host.
- Prefer the `deploy/` production bundle for new deployments.

Use `vm/README.md` and `09-vm-deployment.md` first. AWS-oriented notes remain for historical context, but they are no longer the default production path for this repository.
