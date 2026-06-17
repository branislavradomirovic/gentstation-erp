# GentStationAI Ubuntu Smoke Test Checklist

Run this immediately after a clean deployment or restore.

## Service checks
- [ ] `docker compose ps` shows all expected core services running.
- [ ] `./deploy/scripts/healthcheck.sh` passes.
- [ ] Web, Postgres, Redis, and worker health checks are green.

## App checks
- [ ] Public landing page loads without boot errors.
- [ ] Login page loads and authenticates a known user.
- [ ] Dashboard, Stations, Settings, and AI Reports load.
- [ ] Platform Health loads for a Platform Superadmin only.

## Queue and worker checks
- [ ] AI worker heartbeat is fresh.
- [ ] Telegram worker heartbeat is fresh if enabled.
- [ ] Report scheduler heartbeat is fresh.
- [ ] Queue depth is within expected thresholds.

## Data protection checks
- [ ] Tenant users cannot access Platform Health.
- [ ] Tenant-scoped pages show only local tenant data.
- [ ] Tier-gated CCTV pages are hidden or blocked for Tier 1 tenants.

## Recovery checks
- [ ] `./deploy/scripts/backup.sh` creates a dump and manifest.
- [ ] Latest restore point is visible in the backup directory.
