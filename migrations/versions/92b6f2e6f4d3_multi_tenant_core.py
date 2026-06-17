"""multi tenant core

Revision ID: 92b6f2e6f4d3
Revises: 89a5e1d5e3c2
Create Date: 2024-05-20 11:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "92b6f2e6f4d3"  # pragma: allowlist secret
down_revision = "89a5e1d5e3c2"  # pragma: allowlist secret
branch_labels = None
depends_on = None


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


def _backfill_tenant_id(table_name: str) -> None:
    if table_name == "users":
        # Some live databases already have assignment-integrity triggers on users.
        # Disable user-defined triggers temporarily so legacy rows can be stamped
        # with the default tenant before later cleanup/validation paths run.
        op.execute("ALTER TABLE users DISABLE TRIGGER USER")
        try:
            op.execute("UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL")
        finally:
            op.execute("ALTER TABLE users ENABLE TRIGGER USER")
        return

    op.execute(f"UPDATE {table_name} SET tenant_id = 1 WHERE tenant_id IS NULL")


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints(table_name):
        if constraint.get("name") == constraint_name:
            return True
    return False


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("locale", sa.String(length=32), nullable=False, server_default="en"),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.UniqueConstraint("name", name="uq_tenants_name"),
    )

    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("tier_code", sa.String(length=64), nullable=False, server_default="tier_1_ai_daily_operations"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("billing_cycle", sa.String(length=32), nullable=False, server_default="monthly"),
        sa.Column("billing_currency", sa.String(length=8), nullable=False, server_default="EUR"),
        sa.Column("station_limit", sa.Integer(), nullable=True),
        sa.Column("employee_limit", sa.Integer(), nullable=True),
        sa.Column("camera_limit", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("starts_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "tenant_settings",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_key"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "tenant_feature_flags",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("feature_key", sa.String(length=120), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "feature_key", name="uq_tenant_feature_flags_key"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    op.execute(
        """
        INSERT INTO tenants (id, slug, name, status, timezone, locale, retention_days)
        VALUES (1, 'default', 'Default Tenant', 'active', 'UTC', 'en', 30)
        ON CONFLICT (id) DO UPDATE SET
            slug = EXCLUDED.slug,
            name = EXCLUDED.name,
            status = EXCLUDED.status,
            timezone = EXCLUDED.timezone,
            locale = EXCLUDED.locale,
            retention_days = EXCLUDED.retention_days
        """
    )

    op.execute(
        sa.text(
            """
            INSERT INTO tenant_subscriptions (
                tenant_id, tier_code, status, billing_cycle, billing_currency,
                camera_limit, metadata_json
            )
            VALUES (1, 'tier_1_ai_daily_operations', 'active', 'monthly', 'EUR', 0, '{"source": "phase2_migration"}'::jsonb)
            ON CONFLICT (tenant_id) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO tenant_settings (tenant_id, key, value_json)
            VALUES
                (1, 'timezone', '"UTC"'::jsonb),
                (1, 'locale', '"en"'::jsonb),
                (1, 'retention_days', '30'::jsonb)
            ON CONFLICT (tenant_id, key) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO tenant_feature_flags (tenant_id, feature_key, is_enabled, config_json)
            VALUES
                (1, 'tier_1_ai_daily_operations', TRUE, '{}'::jsonb),
                (1, 'tier_2_cctv_intelligence', FALSE, '{}'::jsonb),
                (1, 'telegram_intake', TRUE, '{}'::jsonb),
                (1, 'email_notifications', TRUE, '{}'::jsonb),
                (1, 'report_scheduler', TRUE, '{}'::jsonb)
            ON CONFLICT (tenant_id, feature_key) DO NOTHING
            """
        )
    )

    for table in TENANT_OWNED_TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Integer(), nullable=True))

    for table in TENANT_OWNED_TABLES:
        _backfill_tenant_id(table)

    for table in TENANT_OWNED_TABLES:
        op.create_foreign_key(
            f"fk_{table}_tenant",
            table,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if _constraint_exists("station_categories", "uq_station_categories_name"):
        op.drop_constraint("uq_station_categories_name", "station_categories", type_="unique")
    op.create_unique_constraint(
        "uq_station_categories_tenant_name",
        "station_categories",
        ["tenant_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_station_categories_tenant_name", "station_categories", type_="unique")
    op.create_unique_constraint("uq_station_categories_name", "station_categories", ["name"])

    for table in reversed(TENANT_OWNED_TABLES):
        op.drop_constraint(f"fk_{table}_tenant", table, type_="foreignkey")
        op.drop_column(table, "tenant_id")

    op.drop_table("tenant_feature_flags")
    op.drop_table("tenant_settings")
    op.drop_table("tenant_subscriptions")
    op.drop_table("tenants")
