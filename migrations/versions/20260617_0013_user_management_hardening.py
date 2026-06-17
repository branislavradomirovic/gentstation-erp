"""user management hardening

Revision ID: 20260617_0013
Revises: 20260617_0012
Create Date: 2026-06-18 00:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "20260617_0013"
down_revision = "20260617_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "lifecycle_state",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("phone", sa.String(length=64), nullable=True))

    op.execute(
        """
        UPDATE users
        SET lifecycle_state = CASE
            WHEN COALESCE(is_active, TRUE) = FALSE THEN 'suspended'
            WHEN COALESCE(force_password_change, FALSE) = TRUE THEN 'password_reset_required'
            ELSE 'active'
        END
        """
    )

    op.create_index(
        "idx_users_tenant_lifecycle_state",
        "users",
        ["tenant_id", "lifecycle_state"],
    )


def downgrade() -> None:
    op.drop_index("idx_users_tenant_lifecycle_state", table_name="users")
    op.drop_column("users", "phone")
    op.drop_column("users", "lifecycle_state")
