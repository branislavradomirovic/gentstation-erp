"""baseline

Revision ID: 89a5e1d5e3c2
Revises:
Create Date: 2024-05-20 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "89a5e1d5e3c2"  # pragma: allowlist secret
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("station_categories"):
        op.create_table(
            "station_categories",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("color", sa.String(length=50), server_default="#808080", nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_station_categories_name"),
        )

    if not _table_exists("regions"):
        op.create_table(
            "regions",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("stations"):
        op.create_table(
            "stations",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("region_id", sa.Integer(), nullable=True),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("physical_address", sa.Text(), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("lat", sa.Numeric(precision=10, scale=8), nullable=True),
            sa.Column("lon", sa.Numeric(precision=11, scale=8), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["station_categories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("username", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("role", sa.String(length=100), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("surname", sa.String(length=255), nullable=True),
            sa.Column("station_id", sa.Integer(), nullable=True),
            sa.Column("region_id", sa.Integer(), nullable=True),
            sa.Column("manager_user_id", sa.Integer(), nullable=True),
            sa.Column("telegram_chat_id", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=True),
            sa.Column("locked_until", sa.DateTime(), nullable=True),
            sa.Column("dark_mode_enabled", sa.Boolean(), server_default=sa.text("FALSE"), nullable=True),
            sa.Column("force_password_change", sa.Boolean(), server_default=sa.text("FALSE"), nullable=True),
            sa.ForeignKeyConstraint(["manager_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
            sa.UniqueConstraint("username"),
        )

    if not _table_exists("sessions"):
        op.create_table(
            "sessions",
            sa.Column("token", sa.String(length=500), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )

    if not _table_exists("activity_logs"):
        op.create_table(
            "activity_logs",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("user_name", sa.String(length=255), nullable=True),
            sa.Column("action", sa.String(length=255), nullable=True),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("submissions"):
        op.create_table(
            "submissions",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("station_id", sa.Integer(), nullable=True),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("video_path", sa.Text(), nullable=True),
            sa.Column("audio_path", sa.Text(), nullable=True),
            sa.Column("role", sa.String(length=100), nullable=True),
            sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("processed", sa.Integer(), server_default="0", nullable=True),
            sa.Column("status", sa.String(length=50), server_default="pending", nullable=True),
            sa.Column("processing_started_ts", sa.DateTime(), nullable=True),
            sa.Column("retry_count", sa.Integer(), server_default="0", nullable=True),
            sa.Column("processed_ts", sa.DateTime(), nullable=True),
            sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("file_unique_id", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["employee_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        )

    if not _table_exists("slow_query_logs"):
        op.create_table(
            "slow_query_logs",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("query_text", sa.Text(), nullable=True),
            sa.Column("duration_seconds", sa.Numeric(precision=10, scale=4), nullable=True),
            sa.Column("params", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("system_settings"):
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(length=255), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("key"),
        )

    if not _table_exists("worker_health_logs"):
        op.create_table(
            "worker_health_logs",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("worker_name", sa.String(length=50), nullable=True),
            sa.Column("cpu_percent", sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column("memory_mb", sa.Numeric(precision=10, scale=2), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("redis_health_logs"):
        op.create_table(
            "redis_health_logs",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("is_online", sa.Boolean(), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("ai_inference_latency"):
        op.create_table(
            "ai_inference_latency",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("model_name", sa.String(length=255), nullable=True),
            sa.Column("latency_seconds", sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column("submission_id", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        )

    if not _table_exists("scheduled_reports"):
        op.create_table(
            "scheduled_reports",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("report_type", sa.String(length=32), nullable=False),
            sa.Column("scope_type", sa.String(length=32), nullable=False),
            sa.Column("scope_id", sa.Integer(), nullable=True),
            sa.Column("recipient_user_id", sa.Integer(), nullable=True),
            sa.Column("period_start", sa.DateTime(), nullable=False),
            sa.Column("period_end", sa.DateTime(), nullable=False),
            sa.Column("scheduled_for", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
            sa.Column("delivery_channel", sa.String(length=32), nullable=True),
            sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "report_type",
                "scope_type",
                "scope_id",
                "recipient_user_id",
                "period_start",
                "period_end",
                name="uq_scheduled_report_window",
            ),
            sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        )

    if not _table_exists("ai_jobs"):
        op.create_table(
            "ai_jobs",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("job_type", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=50), server_default="pending", nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("ai_reports"):
        op.create_table(
            "ai_reports",
            sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("report_role", sa.String(length=100), nullable=True),
            sa.Column("station_id", sa.Integer(), nullable=True),
            sa.Column("region_id", sa.Integer(), nullable=True),
            sa.Column("report_text", sa.Text(), nullable=True),
            sa.Column("sentiment", sa.Numeric(precision=4, scale=2), nullable=True),
            sa.Column("safety_score", sa.Integer(), nullable=True),
            sa.Column("cleanliness_score", sa.Integer(), nullable=True),
            sa.Column("staff_score", sa.Integer(), nullable=True),
            sa.Column("efficiency_score", sa.Integer(), nullable=True),
            sa.Column("customer_score", sa.Integer(), nullable=True),
            sa.Column("incidents_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("kpi_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("trend", sa.String(length=50), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        )


def downgrade() -> None:
    op.drop_table("ai_reports")
    op.drop_table("ai_jobs")
    op.drop_table("scheduled_reports")
    op.drop_table("ai_inference_latency")
    op.drop_table("redis_health_logs")
    op.drop_table("worker_health_logs")
    op.drop_table("system_settings")
    op.drop_table("slow_query_logs")
    op.drop_table("submissions")
    op.drop_table("activity_logs")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("stations")
    op.drop_table("regions")
    op.drop_table("station_categories")
