"""reporting schedule hierarchy

Revision ID: 20260617_0012
Revises: 20260617_0011
Create Date: 2026-06-17 23:55:00.000000

"""

from alembic import op


revision = "20260617_0012"
down_revision = "20260617_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
                ('Employee Weekly Summary', 'weekly', 'employee', '20:00', 4, NULL, FALSE, '["email","telegram"]', '{"seed_key":"employee_weekly"}'),
                ('Employee Monthly Summary', 'monthly', 'employee', '20:00', NULL, 1, TRUE, '["email","telegram"]', '{"seed_key":"employee_monthly"}'),
                ('Station Weekly Summary', 'weekly', 'station', '20:15', 4, NULL, FALSE, '["email","telegram"]', '{"seed_key":"station_weekly"}'),
                ('Station Monthly Summary', 'monthly', 'station', '20:15', NULL, 1, TRUE, '["email","telegram"]', '{"seed_key":"station_monthly"}'),
                ('Region Weekly Summary', 'weekly', 'region', '20:30', 4, NULL, FALSE, '["email","telegram"]', '{"seed_key":"region_weekly"}'),
                ('Region Monthly Summary', 'monthly', 'region', '20:30', NULL, 1, TRUE, '["email","telegram"]', '{"seed_key":"region_monthly"}')
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
        WHERE (rs.report_type, rs.scope_type) IN (
            ('weekly', 'employee'),
            ('monthly', 'employee'),
            ('weekly', 'station'),
            ('monthly', 'station'),
            ('weekly', 'region'),
            ('monthly', 'region')
        )
        ON CONFLICT (tenant_id, schedule_id, recipient_role, scope_type, scope_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM report_subscriptions
        WHERE scope_id = 0
          AND (schedule_id IN (
              SELECT id
              FROM report_schedules
              WHERE (report_type, scope_type) IN (
                  ('weekly', 'employee'),
                  ('monthly', 'employee'),
                  ('weekly', 'station'),
                  ('monthly', 'station'),
                  ('weekly', 'region'),
                  ('monthly', 'region')
              )
          ))
        """
    )
    op.execute(
        """
        DELETE FROM report_schedules
        WHERE (report_type, scope_type) IN (
            ('weekly', 'employee'),
            ('monthly', 'employee'),
            ('weekly', 'station'),
            ('monthly', 'station'),
            ('weekly', 'region'),
            ('monthly', 'region')
        )
        """
    )
