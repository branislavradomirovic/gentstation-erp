# 12. Sensitive Package Notes

This handoff folder now includes a real environment file for deployment handoff:

- `vm/.env.production.actual`

That file contains live secrets and should be shared only over an approved secure channel.

Current status of the one-folder handoff:

- VM deployment instructions: included
- VM Docker Compose stack: included
- Sanitized production env template: included
- Real environment file with secrets: included
- PostgreSQL dump: included as `gentstation_backup.dump`

Database dump details:

- File: `deployment-handoff/gentstation_backup.dump`
- Format: PostgreSQL custom dump created with `pg_dump -Fc`
- Source database: `gentstation`

This handoff folder now contains the core items needed for a one-folder VM deployment transfer:

- VM deployment documentation
- Docker Compose stack for VM deployment
- sanitized production environment template
- real environment file with live secrets
- PostgreSQL dump with live application data

Recommended next step:

- share this folder only through an approved secure channel because it contains live credentials and production data.
