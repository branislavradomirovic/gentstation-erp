# 09. Single-VM Deployment

## Recommended use case

This is the easiest deployment model if the external team wants to recreate the application quickly on one cloud VM rather than build a full AWS-managed platform first.

Recommended target examples:

- AWS EC2
- Azure VM
- Google Compute Engine
- any Linux VM with Docker and Docker Compose support

## Deployment model

Run the full stack on one Linux VM using Docker Compose:

- application web container
- PostgreSQL container
- Redis container
- AI worker container
- Telegram worker container if needed

This is the fastest path to recreate the environment and is the closest fit to how the repository was already structured for container-based local/full-stack use.

## Recommended VM baseline

Suggested starting size:

- 4 vCPU
- 8 GB RAM
- 80+ GB SSD
- Ubuntu 22.04 LTS or Ubuntu 24.04 LTS

If AI/video workloads are heavy, increase CPU and RAM.

## Files provided for VM deployment

Use these files from this handoff package:

- `vm/docker-compose.vm.yml`
- `vm/.env.vm.example`
- `vm/.env.production.template`

These files are intended to be used in place from the `deployment-handoff/vm/` folder, or adapted carefully by the external team.

## Required prerequisites on the VM

Install:

- Docker Engine
- Docker Compose plugin
- Git

Optional but useful:

- `ufw`
- `nginx` if they want a reverse proxy in front of Streamlit

## Deployment steps

### Step 1. Clone the repository

The team should clone the exact release tag or commit provided by the application owner.

### Step 2. Prepare VM deployment files

Recommended:

- copy `deployment-handoff/vm/.env.vm.example` to `.env` in the repo root
- leave `deployment-handoff/vm/docker-compose.vm.yml` in place and run it with `-f`

Important:

- the provided compose file uses paths relative to `deployment-handoff/vm/`
- if the team copies the compose file to another location, they must also update the relative `build` and volume paths inside it

### Step 3. Populate `.env`

The team must replace placeholder values with real values, especially:

- database credentials
- initial admin credentials
- SMTP credentials if email is enabled
- Telegram bot token if Telegram is enabled
- `APP_LOGIN_URL`
- `OLLAMA_BASE_URL`

### Step 4. Restore production database data if required

If the goal is to recreate the current live environment including users, stations, and historical data, the owner must provide a PostgreSQL dump.

See:

- `10-data-transfer-and-db-restore.md`

Without a database dump, the deployment will start with an empty database schema only.

### Step 5. Start infrastructure and application

The simplest startup command is:

```bash
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env up -d --build
```

If Telegram is enabled, include the Telegram profile:

```bash
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env --profile telegram up -d --build
```

### Step 6. Validate startup

Confirm:

- `postgres` is healthy
- `schema-init` completed successfully
- `redis` is healthy
- `app` is running
- `ai-worker` is running if AI is enabled
- `report-scheduler` is running
- `telegram-worker` is running if Telegram is enabled

Use:

```bash
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env ps
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env logs app
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env logs ai-worker
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env logs report-scheduler
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env --profile telegram logs telegram-worker
```

The `telegram-worker` service is profile-gated and will only start when the `telegram` profile is enabled.

### Step 7. Open the application

Default direct access is:

```text
http://<vm-ip>:8501
```

For production-like access, the team should place Nginx or a cloud load balancer in front and expose HTTPS.

## Notes on Ollama in a VM deployment

The VM approach can work in two ways:

1. Ollama runs outside Docker on the same VM
2. Ollama is hosted elsewhere and reachable by URL

If Ollama runs on the same VM outside Docker, `OLLAMA_BASE_URL` may need to be set to a Docker-reachable host address such as:

```text
http://host.docker.internal:11434
```

or a concrete bridge/host IP depending on Linux networking choices.

The deployment team should verify actual connectivity from the `ai-worker` container.

## Notes on persistence

This VM deployment stores persistent data in Docker volumes for:

- PostgreSQL
- Redis

and bind-mounted directories for:

- `uploads`
- `downloads`

If the team rebuilds or migrates the VM, those data locations must be preserved or backed up.

## What this VM path optimizes for

- fastest recreation
- lowest infrastructure complexity
- easiest operational handoff

## What this VM path does not optimize for

- high availability
- managed failover
- horizontal scaling
- strict separation of stateful services
