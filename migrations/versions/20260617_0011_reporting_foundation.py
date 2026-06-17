"""reporting foundation

Revision ID: 20260617_0011
Revises: 20260617_0010
Create Date: 2026-06-17 23:30:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260617_0011"
down_revision = "20260617_0010"
branch_labels = None
depends_on = None

REPORTING_TABLES = [
    "report_schedules",
    "report_subscriptions",
    "report_delivery_attempts",
]


def upgrade() -> None:
    op.create_table(
        "report_schedules",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("send_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("weekly_day", sa.Integer(), nullable=True),
        sa.Column("monthly_day", sa.Integer(), nullable=True),
        sa.Column("use_last_day", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("channels_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("tenant_id", "report_type", "scope_type", name="uq_report_schedule_scope"),
    )

    op.create_table(
        "report_subscriptions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", sa.Integer(), sa.ForeignKey("report_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("recipient_role", sa.String(length=100), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("delivery_channels_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "report_delivery_attempts",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_report_id", sa.Integer(), sa.ForeignKey("scheduled_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_schedule_id", sa.Integer(), sa.ForeignKey("report_schedules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_subscription_id", sa.Integer(), sa.ForeignKey("report_subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attempted_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_unique_constraint(
        "uq_report_subscription_scope",
        "report_subscriptions",
        ["tenant_id", "schedule_id", "recipient_role", "scope_type", "scope_id"],
    )

    for table in REPORTING_TABLES:
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
        "idx_report_schedules_tenant_scope_type",
        "report_schedules",
        ["tenant_id", "scope_type"],
    )
    op.create_index(
        "idx_report_schedules_tenant_enabled_report_type",
        "report_schedules",
        ["tenant_id", "enabled", "report_type"],
    )
    op.create_index(
        "idx_report_subscriptions_tenant_scope",
        "report_subscriptions",
        ["tenant_id", "scope_type", "scope_id"],
    )
    op.create_index(
        "idx_report_subscriptions_recipient_enabled",
        "report_subscriptions",
        ["recipient_user_id", "enabled"],
    )
    op.create_index(
        "idx_report_delivery_attempts_tenant_report_type",
        "report_delivery_attempts",
        ["tenant_id", "report_type"],
    )
    op.create_index(
        "idx_report_delivery_attempts_recipient_attempted_at",
        "report_delivery_attempts",
        ["recipient_user_id", "attempted_at"],
    )

    op.execute(
        """
        INSERT INTO report_schedules (
            tenant_id, name, report_type, scope_type, enabled, send_time, timezone,
            weekly_day, monthly_day, use_last_day, channels_json, config_json
        )
        SELECT
            t.id,
            seed.name,
            seed.report_type,
            seed.scope_type,
            TRUE,
            seed.send_time::time,
            COALESCE(t.timezone, 'UTC'),
            seed.weekly_day,
            seed.monthly_day,
            seed.use_last_day,
            seed.channels_json::jsonb,
            seed.config_json::jsonb
        FROM tenants t
        CROSS JOIN (
            VALUES
                ('Employee Daily Report', 'daily', 'employee', '20:00', NULL, NULL, FALSE, '["email","telegram"]', '{"seed_key":"employee_daily"}'),
                ('Station Daily Report', 'daily', 'station', '20:15', NULL, NULL, FALSE, '["email","telegram"]', '{"seed_key":"station_daily"}'),
                ('Region Daily Report', 'daily', 'region', '20:30', NULL, NULL, FALSE, '["email","telegram"]', '{"seed_key":"region_daily"}'),
                ('Company Daily Report', 'daily', 'company', '21:00', NULL, NULL, FALSE, '["email","telegram"]', '{"seed_key":"company_daily"}'),
                ('Company Weekly Summary', 'weekly', 'company', '21:15', 4, NULL, FALSE, '["email","telegram"]', '{"seed_key":"company_weekly"}'),
                ('Company Monthly Summary', 'monthly', 'company', '21:30', NULL, 1, TRUE, '["email","telegram"]', '{"seed_key":"company_monthly"}')
        ) AS seed(name, report_type, scope_type, send_time, weekly_day, monthly_day, use_last_day, channels_json, config_json)
        ON CONFLICT (tenant_id, report_type, scope_type) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO report_subscriptions (
            tenant_id, schedule_id, recipient_role, scope_type, scope_id, enabled, delivery_channels_json
        )
        SELECT
            rs.tenant_id,
            rs.id,
            CASE
                WHEN rs.scope_type = 'employee' THEN 'Employee'
                WHEN rs.scope_type = 'station' THEN 'Gas Station Manager'
                WHEN rs.scope_type = 'region' THEN 'Region Manager'
                ELSE 'General Manager'
            END,
            rs.scope_type,
            0,
            TRUE,
            rs.channels_json
        FROM report_schedules rs
        ON CONFLICT (tenant_id, schedule_id, recipient_role, scope_type, scope_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_report_delivery_attempts_recipient_attempted_at", table_name="report_delivery_attempts")
    op.drop_index("idx_report_delivery_attempts_tenant_report_type", table_name="report_delivery_attempts")
    op.drop_index("idx_report_subscriptions_recipient_enabled", table_name="report_subscriptions")
    op.drop_index("idx_report_subscriptions_tenant_scope", table_name="report_subscriptions")
    op.drop_index("idx_report_schedules_tenant_enabled_report_type", table_name="report_schedules")
    op.drop_index("idx_report_schedules_tenant_scope_type", table_name="report_schedules")
    op.drop_table("report_delivery_attempts")
    op.drop_table("report_subscriptions")
    op.drop_table("report_schedules")
