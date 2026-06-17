"""cctv intelligence

Revision ID: 20260613_0003
Revises: 20260613_0002
Create Date: 2026-06-13 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260613_0003'
down_revision = '92b6f2e6f4d3'  # pragma: allowlist secret
branch_labels = None
depends_on = None

CCTV_TABLES = ["cctv_cameras", "cctv_zones", "cctv_events", "cctv_review_actions"]

def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION gsai_current_tenant_id()
        RETURNS INTEGER
        LANGUAGE plpgsql
        AS $$
        DECLARE
            tenant_value TEXT;
        BEGIN
            tenant_value := current_setting('app.current_tenant_id', true);
            IF tenant_value IS NULL OR btrim(tenant_value) = '' THEN
                RETURN NULL;
            END IF;
            RETURN tenant_value::INTEGER;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION gsai_platform_access_enabled()
        RETURNS BOOLEAN
        LANGUAGE sql
        AS $$
            SELECT COALESCE(NULLIF(current_setting('app.platform_access', true), ''), 'off') = 'on';
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION gsai_assign_tenant_id()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            current_tenant INTEGER;
        BEGIN
            IF gsai_platform_access_enabled() THEN
                RETURN NEW;
            END IF;

            current_tenant := gsai_current_tenant_id();
            IF current_tenant IS NULL THEN
                RAISE EXCEPTION 'Tenant context is required for table %', TG_TABLE_NAME;
            END IF;

            NEW.tenant_id := current_tenant;
            RETURN NEW;
        END;
        $$;
        """
    )

    op.create_table('cctv_cameras',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('stations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('stream_url_secret_ref', sa.String(length=255)),
        sa.Column('camera_type', sa.String(length=50)),
        sa.Column('status', sa.String(length=50), server_default='active'),
        sa.Column('timezone', sa.String(length=50), server_default='UTC'),
        sa.Column('last_seen_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    op.create_table('cctv_zones',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_id', sa.Integer(), sa.ForeignKey('cctv_cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('zone_type', sa.String(length=50)),
        sa.Column('polygon_json', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('active', sa.Boolean(), server_default='TRUE'),
        sa.Column('rules_json', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    op.create_table('cctv_events',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('station_id', sa.Integer(), sa.ForeignKey('stations.id', ondelete='CASCADE')),
        sa.Column('camera_id', sa.Integer(), sa.ForeignKey('cctv_cameras.id', ondelete='SET NULL')),
        sa.Column('zone_id', sa.Integer(), sa.ForeignKey('cctv_zones.id', ondelete='SET NULL')),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('severity', sa.String(length=50), server_default='low'),
        sa.Column('confidence', sa.Numeric(precision=4, scale=2)),
        sa.Column('status', sa.String(length=50), server_default='new'),
        sa.Column('occurred_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('evidence_path', sa.Text()),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    op.create_table('cctv_review_actions',
        sa.Column('id', sa.Integer(), sa.Identity(always=False), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('cctv_events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reviewer_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('comment', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'))
    )

    for table in CCTV_TABLES:
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
    op.create_index('idx_cctv_events_station_id', 'cctv_events', ['station_id'])
    op.create_index('idx_cctv_events_occurred_at', 'cctv_events', ['occurred_at'])
    op.create_index('idx_cctv_events_status', 'cctv_events', ['status'])
    op.create_index('idx_cctv_zones_camera_id', 'cctv_zones', ['camera_id'])

def downgrade() -> None:
    for table in reversed(CCTV_TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS gsai_assign_tenant_id()")
    op.execute("DROP FUNCTION IF EXISTS gsai_platform_access_enabled()")
    op.execute("DROP FUNCTION IF EXISTS gsai_current_tenant_id()")
