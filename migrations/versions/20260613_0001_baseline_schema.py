"""baseline schema

Revision ID: 20260613_0001
Revises:
Create Date: 2026-06-13 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260613_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "station_categories",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=False, server_default="#808080"),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("name", name="uq_station_categories_name"),
    )

    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("regions.id", ondelete="SET NULL")),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("station_categories.id", ondelete="CASCADE")),
        sa.Column("physical_address", sa.Text()),
        sa.Column("email", sa.String(length=255)),
        sa.Column("lat", sa.Numeric(10, 8)),
        sa.Column("lon", sa.Numeric(11, 8)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255)),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE")),
        sa.Column("name", sa.String(length=255)),
        sa.Column("surname", sa.String(length=255)),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id", ondelete="SET NULL")),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("regions.id", ondelete="SET NULL")),
        sa.Column("manager_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("telegram_chat_id", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("failed_attempts", sa.Integer(), server_default="0"),
        sa.Column("locked_until", sa.DateTime()),
        sa.Column("dark_mode_enabled", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("force_password_change", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_user_assignment_integrity()
        RETURNS TRIGGER
        AS $$
        DECLARE
            station_region_id INTEGER;
            manager_role VARCHAR(100);
        BEGIN
            IF NEW.role IN ('Employee', 'Gas Station Supervisor', 'Gas Station Manager') THEN
                IF NEW.station_id IS NULL THEN
                    RAISE EXCEPTION 'Role % requires station_id', NEW.role;
                END IF;

                SELECT region_id INTO station_region_id
                FROM stations
                WHERE id = NEW.station_id;

                IF station_region_id IS NULL THEN
                    RAISE EXCEPTION 'Assigned station % must exist and belong to a region', NEW.station_id;
                END IF;

                NEW.region_id := station_region_id;
            ELSIF NEW.role = 'Region Manager' THEN
                IF NEW.region_id IS NULL THEN
                    RAISE EXCEPTION 'Region Manager requires region_id';
                END IF;
                NEW.station_id := NULL;
            ELSIF NEW.role = 'General Manager' THEN
                NEW.station_id := NULL;
                NEW.region_id := NULL;
                NEW.manager_user_id := NULL;
            END IF;

            IF NEW.manager_user_id IS NOT NULL THEN
                SELECT role INTO manager_role
                FROM users
                WHERE id = NEW.manager_user_id;

                IF manager_role IS NULL THEN
                    RAISE EXCEPTION 'Assigned manager % does not exist', NEW.manager_user_id;
                END IF;

                IF NEW.role = 'Employee' AND manager_role <> 'Gas Station Manager' THEN
                    RAISE EXCEPTION 'Employee must report to Gas Station Manager';
                ELSIF NEW.role = 'Gas Station Manager' AND manager_role <> 'Region Manager' THEN
                    RAISE EXCEPTION 'Gas Station Manager must report to Region Manager';
                ELSIF NEW.role = 'Region Manager' AND manager_role <> 'General Manager' THEN
                    RAISE EXCEPTION 'Region Manager must report to General Manager';
                ELSIF NEW.role = 'General Manager' THEN
                    RAISE EXCEPTION 'General Manager cannot have manager_user_id';
                END IF;
            ELSE
                IF NEW.role = 'Employee' THEN
                    RAISE EXCEPTION 'Employee requires manager_user_id';
                ELSIF NEW.role = 'Gas Station Manager' THEN
                    RAISE EXCEPTION 'Gas Station Manager requires manager_user_id';
                ELSIF NEW.role = 'Region Manager' THEN
                    RAISE EXCEPTION 'Region Manager requires manager_user_id';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_enforce_user_assignment_integrity
        BEFORE INSERT OR UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION enforce_user_assignment_integrity();
        """
    )

    op.create_table(
        "sessions",
        sa.Column("token", sa.String(length=500), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("user_name", sa.String(length=255)),
        sa.Column("action", sa.String(length=255)),
        sa.Column("details", sa.Text()),
        sa.Column("ip_address", sa.String(length=45)),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id", ondelete="CASCADE")),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("video_path", sa.Text()),
        sa.Column("audio_path", sa.Text()),
        sa.Column("role", sa.String(length=100)),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("processed", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(length=50), server_default="pending"),
        sa.Column("processing_started_ts", sa.DateTime()),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("processed_ts", sa.DateTime()),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("file_unique_id", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "ai_alerts",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id", ondelete="CASCADE")),
        sa.Column("severity", sa.String(length=50)),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("status", sa.String(length=50), server_default="new"),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("value", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "redis_health_logs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("is_online", sa.Boolean(), nullable=False),
        sa.Column("details", sa.Text()),
    )

    op.create_table(
        "ai_inference_latency",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("model_name", sa.String(length=255)),
        sa.Column("latency_seconds", sa.Numeric(10, 2)),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="SET NULL")),
    )

    op.create_table(
        "worker_health_logs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("worker_name", sa.String(length=50)),
        sa.Column("cpu_percent", sa.Numeric(5, 2)),
        sa.Column("memory_mb", sa.Numeric(10, 2)),
    )

    op.create_table(
        "scheduled_reports",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.Integer()),
        sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("delivery_channel", sa.String(length=32)),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("error_message", sa.Text()),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "slow_query_logs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("query_text", sa.Text()),
        sa.Column("duration_seconds", sa.Numeric(10, 4)),
        sa.Column("params", sa.Text()),
    )

    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("job_type", sa.String(length=100)),
        sa.Column("status", sa.String(length=50), server_default="pending"),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "ai_reports",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("report_role", sa.String(length=100)),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id", ondelete="CASCADE")),
        sa.Column("region_id", sa.Integer(), sa.ForeignKey("regions.id", ondelete="SET NULL")),
        sa.Column("report_text", sa.Text()),
        sa.Column("sentiment", sa.Numeric(4, 2)),
        sa.Column("safety_score", sa.Integer()),
        sa.Column("cleanliness_score", sa.Integer()),
        sa.Column("staff_score", sa.Integer()),
        sa.Column("efficiency_score", sa.Integer()),
        sa.Column("customer_score", sa.Integer()),
        sa.Column("incidents_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("kpi_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("trend", sa.String(length=50)),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_index("idx_submissions_station_id", "submissions", ["station_id"])
    op.create_index("idx_submissions_processed", "submissions", ["processed"])
    op.create_index("idx_users_manager_user_id", "users", ["manager_user_id"])
    op.create_index("idx_ai_alerts_station_id", "ai_alerts", ["station_id"])
    op.create_index("idx_ai_alerts_created_at", "ai_alerts", ["created_at"])
    op.create_index("idx_activity_logs_timestamp", "activity_logs", ["timestamp"])
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_username", "users", ["username"])
    op.create_index(
        "ux_users_telegram_chat_id_not_null",
        "users",
        ["telegram_chat_id"],
        unique=True,
        postgresql_where=sa.text("telegram_chat_id IS NOT NULL"),
    )
    op.create_index("idx_ai_jobs_status", "ai_jobs", ["status"])
    op.create_index("idx_ai_reports_station_id", "ai_reports", ["station_id"])
    op.create_index("idx_redis_health_logs_timestamp", "redis_health_logs", ["timestamp"])
    op.create_index("idx_ai_latency_timestamp", "ai_inference_latency", ["timestamp"])
    op.create_index("idx_worker_health_timestamp", "worker_health_logs", ["timestamp"])
    op.create_index("idx_slow_queries_timestamp", "slow_query_logs", ["timestamp"])
    op.create_index("idx_scheduled_reports_due", "scheduled_reports", ["status", "scheduled_for"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_scheduled_report_window
        ON scheduled_reports(report_type, scope_type, COALESCE(scope_id, -1), recipient_user_id, period_start, period_end)
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_user_assignment_integrity ON users")
    op.execute("DROP FUNCTION IF EXISTS enforce_user_assignment_integrity()")
    op.execute("DROP INDEX IF EXISTS uq_scheduled_report_window")

    for index_name in (
        "idx_scheduled_reports_due",
        "idx_slow_queries_timestamp",
        "idx_worker_health_timestamp",
        "idx_ai_latency_timestamp",
        "idx_redis_health_logs_timestamp",
        "idx_ai_reports_station_id",
        "idx_ai_jobs_status",
        "ux_users_telegram_chat_id_not_null",
        "idx_users_username",
        "idx_users_email",
        "idx_activity_logs_timestamp",
        "idx_ai_alerts_created_at",
        "idx_ai_alerts_station_id",
        "idx_users_manager_user_id",
        "idx_submissions_processed",
        "idx_submissions_station_id",
    ):
        op.drop_index(index_name, if_exists=True)

    for table_name in (
        "ai_reports",
        "ai_jobs",
        "slow_query_logs",
        "scheduled_reports",
        "worker_health_logs",
        "ai_inference_latency",
        "redis_health_logs",
        "system_settings",
        "ai_alerts",
        "submissions",
        "activity_logs",
        "sessions",
        "users",
        "stations",
        "regions",
        "station_categories",
    ):
        op.drop_table(table_name)
