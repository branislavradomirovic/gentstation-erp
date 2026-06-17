# Legacy VM Production Target

GentStationAI production should run on a dedicated Ubuntu 22.04 or 24.04 server with Docker Engine and the Docker Compose plugin installed.

The current canonical production path is `deploy/docker-compose.prod.yml`.
This VM bundle is retained for legacy or archival reference only.

Use this folder as the authoritative starting point only if you are following
the legacy VM handoff package:

- `docker-compose.vm.yml` keeps `web`, `ai-worker`, `telegram-worker`, and `report-scheduler` as separate services.
- `.env.vm.example` is the safe baseline for single-VM Compose deployments.
- `.env.production.example` is the sanitized production-shaped example for server-only secret entry.

Rules for this target:

- Do not use Render as the production target.
- Do not commit real secrets, dump files, or filled production env files.
- Keep PostgreSQL, Redis, reverse proxy, backups, and optional local Ollama in the Ubuntu deployment design.
- Fill real values only on the server after copying an example to an untracked `.env` file.

Suggested server flow:

1. Copy the repository to the Ubuntu host.
2. Copy `.env.vm.example` or `.env.production.example` to a local untracked `.env`.
3. Fill real secrets on the server only.
4. Run `docker compose -f deploy/docker-compose.prod.yml up -d --build`.

Legacy AWS-oriented handoff notes remain in the parent folder for reference.
