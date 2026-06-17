"""submission media blobs

Revision ID: 20260617_0008
Revises: 20260617_0007
Create Date: 2026-06-17 12:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260617_0008"
down_revision = "20260617_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("video_filename", sa.String(length=255), nullable=True))
    op.add_column("submissions", sa.Column("video_mime_type", sa.String(length=100), nullable=True))
    op.add_column("submissions", sa.Column("video_size_bytes", sa.Integer(), nullable=True))
    op.add_column("submissions", sa.Column("video_checksum", sa.String(length=128), nullable=True))
    op.add_column("submissions", sa.Column("video_blob", sa.LargeBinary(), nullable=True))
    op.add_column("submissions", sa.Column("audio_filename", sa.String(length=255), nullable=True))
    op.add_column("submissions", sa.Column("audio_mime_type", sa.String(length=100), nullable=True))
    op.add_column("submissions", sa.Column("audio_size_bytes", sa.Integer(), nullable=True))
    op.add_column("submissions", sa.Column("audio_checksum", sa.String(length=128), nullable=True))
    op.add_column("submissions", sa.Column("audio_blob", sa.LargeBinary(), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("source_filename", sa.String(length=255), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("source_mime_type", sa.String(length=100), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("source_size_bytes", sa.Integer(), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("source_checksum", sa.String(length=128), nullable=True))
    op.add_column("cctv_analysis_jobs", sa.Column("source_blob", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("cctv_analysis_jobs", "source_blob")
    op.drop_column("cctv_analysis_jobs", "source_checksum")
    op.drop_column("cctv_analysis_jobs", "source_size_bytes")
    op.drop_column("cctv_analysis_jobs", "source_mime_type")
    op.drop_column("cctv_analysis_jobs", "source_filename")
    op.drop_column("submissions", "audio_blob")
    op.drop_column("submissions", "audio_checksum")
    op.drop_column("submissions", "audio_size_bytes")
    op.drop_column("submissions", "audio_mime_type")
    op.drop_column("submissions", "audio_filename")
    op.drop_column("submissions", "video_blob")
    op.drop_column("submissions", "video_checksum")
    op.drop_column("submissions", "video_size_bytes")
    op.drop_column("submissions", "video_mime_type")
    op.drop_column("submissions", "video_filename")
