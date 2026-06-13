"""add multitenant core

Revision ID: 20260613_0002
Revises: 20260613_0001
Create Date: 2026-06-13 12:15:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260613_0002"
down_revision = "20260613_0001"
branch_labels = None
depends_on = None


DEFAULT_TENANT_ID = 1
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default Tenant"


TENANT_OWNED_TABLES = (
    "regions",
    "station_categories",
    "stations",
    "users",
    "sessions",
    "activity_logs",
    "submissions",
    "ai_alerts",
    "ai_inference_latency",
    "scheduled_reports",
    "ai_jobs",
    "ai_reports",
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("locale", sa.String(length=32), nullable=False, server_default="en"),
        sa.Column("billing_email", sa.String(length=255)),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.UniqueConstraint("name", name="uq_tenants_name"),
    )

    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier_code", sa.String(length=64), nullable=False, server_default="tier_1_ai_daily_operations"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("billing_cycle", sa.String(length=32), nullable=False, server_default="monthly"),
        sa.Column("billing_currency", sa.String(length=8), nullable=False, server_default="EUR"),
        sa.Column("station_limit", sa.Integer()),
        sa.Column("employee_limit", sa.Integer()),
        sa.Column("camera_limit", sa.Integer()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("starts_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("ends_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant_id"),
    )

    op.create_table(
        "tenant_settings",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_key"),
    )

    op.create_table(
        "tenant_feature_flags",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(length=120), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "feature_key", name="uq_tenant_feature_flags_key"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO tenants (id, slug, name, status, timezone, locale, retention_days)
            VALUES (:id, :slug, :name, 'active', 'UTC', 'en', 30)
            """
        ).bindparams(id=DEFAULT_TENANT_ID, slug=DEFAULT_TENANT_SLUG, name=DEFAULT_TENANT_NAME)
    )

    for table_name in TENANT_OWNED_TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "tenant_id",
                sa.Integer(),
                nullable=True,
                server_default=str(DEFAULT_TENANT_ID),
            ),
        )
        op.execute(f"UPDATE {table_name} SET tenant_id = {DEFAULT_TENANT_ID} WHERE tenant_id IS NULL")
        op.alter_column(table_name, "tenant_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table_name}_tenant_id_tenants",
            table_name,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            f"idx_{table_name}_tenant_id",
            table_name,
            ["tenant_id"],
        )

    op.create_index("idx_tenants_slug", "tenants", ["slug"], unique=True)
    op.drop_constraint("uq_station_categories_name", "station_categories", type_="unique")
    op.create_unique_constraint(
        "uq_station_categories_tenant_name",
        "station_categories",
        ["tenant_id", "name"],
    )

    op.execute(
        """
        INSERT INTO tenant_subscriptions (
            tenant_id, tier_code, status, billing_cycle, billing_currency,
            station_limit, employee_limit, camera_limit, metadata_json
        )
        VALUES (
            1, 'tier_1_ai_daily_operations', 'active', 'monthly', 'EUR',
            NULL, NULL, 0,
            '{"source":"phase_2_backfill","notes":"Default single-tenant bootstrap"}'
        )
        """
    )

    op.execute(
        """
        INSERT INTO tenant_settings (tenant_id, key, value_json)
        VALUES
            (1, 'timezone', '"UTC"'),
            (1, 'locale', '"en"'),
            (1, 'branding', '{"company_name":"Default Tenant"}'),
            (1, 'retention_days', '30')
        ON CONFLICT (tenant_id, key) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO tenant_feature_flags (tenant_id, feature_key, is_enabled, config_json)
        VALUES
            (1, 'tier_1_ai_daily_operations', TRUE, '{"tier":"tier_1"}'),
            (1, 'tier_2_cctv_intelligence', FALSE, '{"tier":"tier_2"}'),
            (1, 'telegram_intake', TRUE, '{}'),
            (1, 'email_notifications', TRUE, '{}'),
            (1, 'report_scheduler', TRUE, '{}')
        ON CONFLICT (tenant_id, feature_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_station_categories_tenant_name",
        "station_categories",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_station_categories_name",
        "station_categories",
        ["name"],
    )

    for table_name in reversed(TENANT_OWNED_TABLES):
        op.drop_index(f"idx_{table_name}_tenant_id", table_name=table_name, if_exists=True)
        op.drop_constraint(f"fk_{table_name}_tenant_id_tenants", table_name, type_="foreignkey")
        op.drop_column(table_name, "tenant_id")

    op.drop_index("idx_tenants_slug", table_name="tenants", if_exists=True)
    op.drop_table("tenant_feature_flags")
    op.drop_table("tenant_settings")
    op.drop_table("tenant_subscriptions")
    op.drop_table("tenants")
