# GentStationAI Production Runbooks

## Incident: AI Worker is STALE
**Symptoms**: Submissions remain 'pending' for >10 mins; Platform Health shows AI Worker STALE.
1. Log into server.
2. Check logs: `docker compose logs ai-worker --tail=100`.
3. Check memory usage: `docker stats`.
4. Restart service: `docker compose restart ai-worker`.

## Incident: Redis Connectivity Failure
**Symptoms**: Bot won't accept videos; Workers fail to start.
1. Check Redis container: `docker compose ps redis`.
2. Restart Redis: `docker compose restart redis`.
3. Check `REDIS_URL` in `.env`.

## Incident: Full Disk Space
**Symptoms**: Database errors; health checks fail; backups stop completing.
1. Check usage: `df -h`.
2. Inspect Docker growth: `du -sh /var/lib/docker/containers`.
3. Remove expired backups from the configured backup directory if retention cleanup was skipped.
4. Re-run `./deploy/scripts/healthcheck.sh` after recovery.

## Incident: Queue Backlog Growth
**Symptoms**: `healthcheck.sh` fails on queue thresholds; Platform Health shows rising pending submissions or CCTV jobs.
1. Check worker status in **Platform Health** and verify heartbeat age.
2. Inspect logs:
   `docker compose logs ai-worker --tail=100`
   `docker compose logs telegram-worker --tail=100`
   `docker compose logs report-scheduler --tail=100`
3. Confirm Redis is healthy and reachable.
4. If workers are healthy but queue depth keeps rising, increase worker capacity or reduce ingest rate before retrying failed jobs.

## Procedure: Database Migration Failure
1. If a migration fails on deploy, check Alembic status: `docker compose exec web alembic current`.
2. Check logs for the specific SQL error.
3. Resolve manually via `psql` if necessary, then `alembic stamp <revision>`.

## Procedure: Backup
1. Run `./deploy/scripts/backup.sh`.
2. Confirm both `.dump` and `.manifest.json` files were created in the backup directory.
3. Verify retention cleanup left at least one recent restore point.

## Procedure: Emergency Restore
1. Identify the latest healthy timestamp in the backup directory.
2. Run `./deploy/scripts/restore.sh <timestamp>`.
3. Type `RESTORE` when prompted.
4. Verify login, Platform Health, and recent report data after services restart.

## Notes
1. Submission media, CCTV evidence, and integration import blobs are stored in Postgres, not local upload directories.
2. Platform Health is restricted to Platform Superadmins and should not be granted to tenant users.
