# 12. Sensitive Package Notes

This handoff package can include a real environment file for deployment handoff:

- `vm/.env.production.actual`

That file contains live secrets and should be shared only through an approved internal channel.

Current status of the one-folder handoff archive:

- VM deployment instructions: included
- VM Docker Compose stack: included
- Sanitized production env template: included
- Real environment file with secrets: included
- PostgreSQL dump: included as `gentstation_backup.dump`

Important packaging note:

- the hidden `vm/.env*` files are ignored by git
- if the team receives only a repository URL or git checkout, those hidden files will not be present unless they are shared separately
- if the team receives a zipped handoff folder, confirm those hidden files are actually included in the archive

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

- share the complete folder or archive through the approved internal company channel you are using for live credentials and production data.
