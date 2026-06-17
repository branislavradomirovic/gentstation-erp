"""cctv pipeline

Revision ID: 20260613_0004
Revises: 20260613_0003
Create Date: 2026-06-13 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260613_0004'
down_revision = '20260613_0003'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add review_required to cctv_events
    op.add_column('cctv_events', sa.Column('review_required', sa.Boolean(), server_default='FALSE', nullable=False))

    # 2. Create cctv_analysis_jobs
    op.create_table('cctv_analysis_jobs',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_id', sa.Integer(), sa.ForeignKey('cctv_cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending'),
        sa.Column('video_path', sa.Text()),
        sa.Column('error_message', sa.Text()),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # 3. Create cctv_metrics_hourly
    op.create_table('cctv_metrics_hourly',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('stations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_id', sa.Integer(), sa.ForeignKey('cctv_cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=False),
        sa.Column('metric_key', sa.String(length=100), nullable=False),
        sa.Column('metric_value', sa.Numeric(precision=12, scale=4), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    # 4. RLS & Triggers
    for table in ["cctv_analysis_jobs", "cctv_metrics_hourly"]:
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
    op.create_index('idx_cctv_metrics_lookup', 'cctv_metrics_hourly', ['station_id', 'metric_date', 'hour'])
    op.create_index('idx_cctv_jobs_status', 'cctv_analysis_jobs', ['status'])

def downgrade() -> None:
    op.drop_index('idx_cctv_jobs_status', table_name='cctv_analysis_jobs')
    op.drop_index('idx_cctv_metrics_lookup', table_name='cctv_metrics_hourly')
    op.drop_table('cctv_metrics_hourly')
    op.drop_table('cctv_analysis_jobs')
    op.drop_column('cctv_events', 'review_required')
