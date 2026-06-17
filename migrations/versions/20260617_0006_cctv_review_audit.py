"""cctv review audit

Revision ID: 20260617_0006
Revises: 20260613_0005
Create Date: 2026-06-17 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "20260617_0006"
down_revision = "20260613_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cctv_review_actions", sa.Column("from_status", sa.String(length=50), nullable=True))
    op.add_column("cctv_review_actions", sa.Column("to_status", sa.String(length=50), nullable=True))
    op.create_index(
        "idx_cctv_review_actions_event_created_at",
        "cctv_review_actions",
        ["event_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_cctv_review_actions_event_created_at", table_name="cctv_review_actions")
    op.drop_column("cctv_review_actions", "to_status")
    op.drop_column("cctv_review_actions", "from_status")
