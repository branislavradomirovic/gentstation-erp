"""cctv analysis versions

Revision ID: 20260617_0007
Revises: 20260617_0006
Create Date: 2026-06-17 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "20260617_0007"
down_revision = "20260617_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cctv_events", sa.Column("provider_name", sa.String(length=100), nullable=True))
    op.add_column("cctv_events", sa.Column("model_version", sa.String(length=100), nullable=True))
    op.add_column("cctv_events", sa.Column("prompt_version", sa.String(length=100), nullable=True))
    op.add_column("cctv_events", sa.Column("job_id", sa.Integer(), sa.ForeignKey("cctv_analysis_jobs.id", ondelete="SET NULL"), nullable=True))

    op.add_column("cctv_analysis_jobs", sa.Column("provider_name", sa.String(length=100), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("model_version", sa.String(length=100), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("prompt_version", sa.String(length=100), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("evidence_filename", sa.String(length=255), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("evidence_mime_type", sa.String(length=100), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("evidence_size_bytes", sa.Integer(), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("evidence_checksum", sa.String(length=128), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("evidence_blob", sa.LargeBinary(), nullable=True))

    op.add_column("cctv_metrics_hourly", sa.Column("confidence", sa.Numeric(precision=4, scale=2), nullable=True))
    op.add_column("cctv_metrics_hourly", sa.Column("provider_name", sa.String(length=100), nullable=True))
    op.add_column("cctv_metrics_hourly", sa.Column("model_version", sa.String(length=100), nullable=True))
    op.add_column("cctv_metrics_hourly", sa.Column("prompt_version", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("cctv_metrics_hourly", "prompt_version")
    op.drop_column("cctv_metrics_hourly", "model_version")
    op.drop_column("cctv_metrics_hourly", "provider_name")
    op.drop_column("cctv_metrics_hourly", "confidence")

    op.drop_column("cctv_analysis_jobs", "evidence_blob")
    op.drop_column("cctv_analysis_jobs", "evidence_checksum")
    op.drop_column("cctv_analysis_jobs", "evidence_size_bytes")
    op.drop_column("cctv_analysis_jobs", "evidence_mime_type")
    op.drop_column("cctv_analysis_jobs", "evidence_filename")
    op.drop_column("cctv_analysis_jobs", "prompt_version")
    op.drop_column("cctv_analysis_jobs", "model_version")
    op.drop_column("cctv_analysis_jobs", "provider_name")

    op.drop_column("cctv_events", "job_id")
    op.drop_column("cctv_events", "prompt_version")
    op.drop_column("cctv_events", "model_version")
    op.drop_column("cctv_events", "provider_name")
