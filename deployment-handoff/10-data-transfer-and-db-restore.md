# 10. Data Transfer And Database Restore

## Goal

This document explains what must be shared if the external team needs a full copy of the current environment, including PostgreSQL content such as:

- users
- stations
- regions
- settings
- reports
- audit data
- other application records

## Important distinction

Application deployment files alone do not include live database content.

To reproduce the actual current environment, the owner must also provide:

- a PostgreSQL database dump
- any required uploaded/generated files
- the production `.env` values or equivalent secrets delivered securely

## Recommended data transfer package

The owner should share these items securely:

1. application source code or repository access
2. the `deployment-handoff` folder
3. a PostgreSQL dump file
4. a secure secrets handoff
5. any persistent file assets if needed

## PostgreSQL dump expectations

Preferred format:

- `pg_dump` custom format

Typical example produced by the owner:

```bash
pg_dump -Fc -h <source-host> -U <source-user> -d <source-db> -f gentstation_backup.dump
```

Alternative plain SQL format is acceptable but less flexible.

## Restore target

In the VM deployment, PostgreSQL runs in the `postgres` container.

The team should:

1. start the stack or at least the `postgres` service
2. create the target database if needed
3. restore the dump into that database

## Example restore workflow

Custom format example:

```bash
docker compose -f deployment-handoff/vm/docker-compose.vm.yml --env-file .env up -d postgres
docker cp gentstation_backup.dump gentstation-postgres:/tmp/gentstation_backup.dump
docker exec -it gentstation-postgres pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists /tmp/gentstation_backup.dump
```

If shell variable expansion inside the container is inconvenient, the team can replace `$DB_USER` and `$DB_NAME` with explicit values.

Plain SQL example:

```bash
cat gentstation_backup.sql | docker exec -i gentstation-postgres psql -U <db_user> -d <db_name>
```

## Restore order recommendation

1. prepare `.env`
2. start `postgres` and `redis`
3. restore the PostgreSQL dump
4. start the `app`
5. verify login and core pages
6. start `ai-worker` and `telegram-worker` if required

## Uploaded/generated file assets

If the current environment relies on files stored outside PostgreSQL, the owner must also share them.

Candidate locations in this project:

- `uploads/`
- `downloads/`

If these folders contain important operational content, they should be copied to the VM before full go-live.

## Secure transfer recommendation

Do not send secrets or database dumps by plain email.

Recommended options:

- secure company file transfer
- encrypted archive with separate password delivery
- private cloud storage with short-lived access
- secrets communicated separately through an approved secure channel

## Validation after restore

After restore, confirm:

- expected users exist
- stations and regions exist
- login works
- dashboards load
- map view loads
- worker services start without schema mismatch errors
