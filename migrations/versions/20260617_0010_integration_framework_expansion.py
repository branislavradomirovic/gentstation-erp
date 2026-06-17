"""integration framework expansion

Revision ID: 20260617_0010
Revises: 20260617_0008
Create Date: 2026-06-17 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260617_0010"
down_revision = "20260617_0008"
branch_labels = None
depends_on = None

INTEGRATION_TABLES = [
    "integration_station_mappings",
    "integration_import_batches",
]


def upgrade() -> None:
    op.add_column("integrations", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("integrations", sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("integrations", sa.Column("secret_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "integration_station_mappings",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_station_id", sa.String(length=255), nullable=False),
        sa.Column("external_location_id", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "integration_id", "station_id", name="uq_integration_station_mapping_station"),
        sa.UniqueConstraint("tenant_id", "integration_id", "external_station_id", name="uq_integration_station_mapping_external_station"),
    )

    op.create_table(
        "integration_import_batches",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", sa.Integer(), sa.ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_type", sa.String(length=50), server_default="csv_placeholder", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=True),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_mime_type", sa.String(length=100), nullable=True),
        sa.Column("source_size_bytes", sa.Integer(), nullable=True),
        sa.Column("source_checksum", sa.String(length=128), nullable=True),
        sa.Column("source_blob", sa.LargeBinary(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    for table in INTEGRATION_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
        op.execute(f"""
            CREATE POLICY "{table}_tenant_isolation_policy" ON "{table}"
            USING (gsai_platform_access_enabled() OR tenant_id = gsai_current_tenant_id())
            WITH CHECK (gsai_platform_access_enabled() OR tenant_id = gsai_current_tenant_id());
        """)
        op.execute(f"""
            CREATE TRIGGER "trg_{table}_assign_tenant_id"
            BEFORE INSERT OR UPDATE ON "{table}"
            FOR EACH ROW EXECUTE FUNCTION gsai_assign_tenant_id();
        """)

    op.create_index(
        "idx_integration_station_mapping_lookup",
        "integration_station_mappings",
        ["integration_id", "external_station_id"],
    )
    op.create_index(
        "idx_integration_import_batches_status",
        "integration_import_batches",
        ["integration_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_integration_import_batches_status", table_name="integration_import_batches")
    op.drop_index("idx_integration_station_mapping_lookup", table_name="integration_station_mappings")
    op.drop_table("integration_import_batches")
    op.drop_table("integration_station_mappings")
    op.drop_column("integrations", "secret_refs_json")
    op.drop_column("integrations", "metadata_json")
    op.drop_column("integrations", "display_name")
