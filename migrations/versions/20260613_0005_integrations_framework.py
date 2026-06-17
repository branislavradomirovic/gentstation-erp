"""integrations framework

Revision ID: 20260613_0005
Revises: 20260613_0004
Create Date: 2026-06-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260613_0005'
down_revision = '20260613_0004'
branch_labels = None
depends_on = None

INTEGRATION_TABLES = ["integrations", "integration_events"]

def upgrade() -> None:
    op.create_table('integrations',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('integration_type', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='active'),
        sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('secret_ref', sa.String(length=255)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('tenant_id', 'integration_type', 'provider', name='uq_integrations_type_provider')
    )

    op.create_table('integration_events',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('integration_id', sa.Integer(), sa.ForeignKey('integrations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_id', sa.String(length=255)),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('stations.id', ondelete='CASCADE')),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    for table in INTEGRATION_TABLES:
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

    # Indexes
    op.create_index('idx_integration_events_lookup', 'integration_events', ['station_id', 'occurred_at'])
    op.create_index('idx_integration_events_type', 'integration_events', ['event_type'])

def downgrade() -> None:
    op.drop_table('integration_events')
    op.drop_table('integrations')
