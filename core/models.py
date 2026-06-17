from sqlalchemy import (
    Boolean,
    Date,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    JSON,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, Identity(always=False), primary_key=True)
    slug = Column(String(120), unique=True, nullable=False)
    name = Column(String(255), unique=True, nullable=False)
    status = Column(String(32), nullable=False, default="active")
    timezone = Column(String(64), nullable=False, default="UTC")
    locale = Column(String(32), nullable=False, default="en")
    billing_email = Column(String(255))
    retention_days = Column(Integer, nullable=False, default=30)
    metadata_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant_id"),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    tier_code = Column(String(64), nullable=False, default="tier_1_ai_daily_operations")
    status = Column(String(32), nullable=False, default="active")
    billing_cycle = Column(String(32), nullable=False, default="monthly")
    billing_currency = Column(String(8), nullable=False, default="EUR")
    station_limit = Column(Integer)
    employee_limit = Column(Integer)
    camera_limit = Column(Integer)
    metadata_json = Column(JSONB)
    starts_at = Column(DateTime, server_default=func.now())
    ends_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TenantSetting(Base):
    __tablename__ = "tenant_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_tenant_settings_key"),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    key = Column(String(120), nullable=False)
    value_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class TenantFeatureFlag(Base):
    __tablename__ = "tenant_feature_flags"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_key", name="uq_tenant_feature_flags_key"),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    feature_key = Column(String(120), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=False)
    config_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Region(Base):
    __tablename__ = "regions"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class StationCategory(Base):
    __tablename__ = "station_categories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_station_categories_tenant_name"),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(255), nullable=False)
    color = Column(String(50), nullable=False, default="#808080")
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Station(Base):
    __tablename__ = "stations"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(255), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"))
    physical_address = Column(Text)
    email = Column(String(255))
    lat = Column(Numeric(10, 8))
    lon = Column(Numeric(11, 8))
    category_id = Column(
        Integer, ForeignKey("station_categories.id", ondelete="CASCADE")
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    username = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    name = Column(String(255))
    surname = Column(String(255))
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"))
    manager_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    phone = Column(String(64))
    telegram_chat_id = Column(String(255))
    lifecycle_state = Column(String(32), nullable=False, default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    dark_mode_enabled = Column(Boolean, default=False)
    force_password_change = Column(Boolean, default=False)


class SessionToken(Base):
    __tablename__ = "sessions"

    token = Column(String(500), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_name = Column(String(255))
    action = Column(String(255))
    details = Column(Text)
    ip_address = Column(String(45))
    timestamp = Column(DateTime, server_default=func.now())


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    employee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    video_path = Column(Text)
    video_filename = Column(String(255))
    video_mime_type = Column(String(100))
    video_size_bytes = Column(Integer)
    video_checksum = Column(String(128))
    video_blob = Column(LargeBinary)
    audio_path = Column(Text)
    audio_filename = Column(String(255))
    audio_mime_type = Column(String(100))
    audio_size_bytes = Column(Integer)
    audio_checksum = Column(String(128))
    audio_blob = Column(LargeBinary)
    role = Column(String(100))
    timestamp = Column(DateTime, server_default=func.now())
    processed = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    processing_started_ts = Column(DateTime)
    retry_count = Column(Integer, default=0)
    processed_ts = Column(DateTime)
    data_json = Column(JSONB)
    file_unique_id = Column(Text)
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SlowQueryLog(Base):
    __tablename__ = "slow_query_logs"

    id = Column(Integer, Identity(always=False), primary_key=True)
    timestamp = Column(DateTime, server_default=func.now())
    query_text = Column(Text)
    duration_seconds = Column(Numeric(10, 4))
    params = Column(Text)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WorkerHealthLog(Base):
    __tablename__ = "worker_health_logs"

    id = Column(Integer, Identity(always=False), primary_key=True)
    timestamp = Column(DateTime, server_default=func.now())
    worker_name = Column(String(50))
    cpu_percent = Column(Numeric(5, 2))
    memory_mb = Column(Numeric(10, 2))


class RedisHealthLog(Base):
    __tablename__ = "redis_health_logs"

    id = Column(Integer, Identity(always=False), primary_key=True)
    timestamp = Column(DateTime, server_default=func.now())
    is_online = Column(Boolean, nullable=False)
    details = Column(Text)


class AIInferenceLatency(Base):
    __tablename__ = "ai_inference_latency"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    timestamp = Column(DateTime, server_default=func.now())
    model_name = Column(String(255))
    latency_seconds = Column(Numeric(10, 2))
    submission_id = Column(Integer, ForeignKey("submissions.id", ondelete="CASCADE"))


class AIAlert(Base):
    __tablename__ = "ai_alerts"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    severity = Column(String(50))
    message = Column(Text)
    status = Column(String(50), default="new")
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"
    __table_args__ = (
        UniqueConstraint(
            "report_type",
            "scope_type",
            "scope_id",
            "recipient_user_id",
            "period_start",
            "period_end",
            name="uq_scheduled_report_window",
        ),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    report_type = Column(String(32), nullable=False)
    scope_type = Column(String(32), nullable=False)
    scope_id = Column(Integer)
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    delivery_channel = Column(String(32))
    payload_json = Column(JSONB)
    error_message = Column(Text)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReportSchedule(Base):
    __tablename__ = "report_schedules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "report_type",
            "scope_type",
            name="uq_report_schedule_scope",
        ),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(120), nullable=False)
    report_type = Column(String(32), nullable=False)
    scope_type = Column(String(32), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    send_time = Column(Time, nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")
    weekly_day = Column(Integer)
    monthly_day = Column(Integer)
    use_last_day = Column(Boolean, nullable=False, default=False)
    channels_json = Column(JSONB)
    config_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReportSubscription(Base):
    __tablename__ = "report_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "schedule_id",
            "recipient_role",
            "scope_type",
            "scope_id",
            name="uq_report_subscription_scope",
        ),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id = Column(
        Integer, ForeignKey("report_schedules.id", ondelete="CASCADE"), nullable=False
    )
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    recipient_role = Column(String(100))
    scope_type = Column(String(32), nullable=False)
    scope_id = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    delivery_channels_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ReportDeliveryAttempt(Base):
    __tablename__ = "report_delivery_attempts"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_report_id = Column(
        Integer, ForeignKey("scheduled_reports.id", ondelete="SET NULL")
    )
    report_schedule_id = Column(
        Integer, ForeignKey("report_schedules.id", ondelete="SET NULL")
    )
    report_subscription_id = Column(
        Integer, ForeignKey("report_subscriptions.id", ondelete="SET NULL")
    )
    report_type = Column(String(32), nullable=False)
    scope_type = Column(String(32), nullable=False)
    scope_id = Column(Integer)
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    channel = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    error_message = Column(Text)
    payload_json = Column(JSONB)
    attempted_at = Column(DateTime, server_default=func.now(), nullable=False)
    delivered_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    job_type = Column(String(100))
    status = Column(String(50), default="pending")
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AIReport(Base):
    __tablename__ = "ai_reports"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(DateTime, server_default=func.now())
    report_role = Column(String(100))
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="SET NULL"))
    report_text = Column(Text)
    sentiment = Column(Numeric(4, 2))
    safety_score = Column(Integer)
    cleanliness_score = Column(Integer)
    staff_score = Column(Integer)
    efficiency_score = Column(Integer)
    customer_score = Column(Integer)
    incidents_json = Column(JSONB)
    kpi_json = Column(JSONB)
    trend = Column(String(50))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CCTVCamera(Base):
    __tablename__ = "cctv_cameras"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    stream_url_secret_ref = Column(String(255))
    camera_type = Column(String(50)) # dome, bullet, 360
    status = Column(String(50), default="active")
    timezone = Column(String(50), default="UTC")
    last_seen_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CCTVZone(Base):
    __tablename__ = "cctv_zones"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    camera_id = Column(Integer, ForeignKey("cctv_cameras.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    zone_type = Column(String(50)) # pump, entrance, shop, restricted
    polygon_json = Column(JSONB)
    active = Column(Boolean, default=True)
    rules_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CCTVEvent(Base):
    __tablename__ = "cctv_events"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    job_id = Column(Integer, ForeignKey("cctv_analysis_jobs.id", ondelete="SET NULL"))
    camera_id = Column(Integer, ForeignKey("cctv_cameras.id", ondelete="SET NULL"))
    zone_id = Column(Integer, ForeignKey("cctv_zones.id", ondelete="SET NULL"))
    event_type = Column(String(100), nullable=False)
    severity = Column(String(50), default="low")
    confidence = Column(Numeric(4, 2))
    status = Column(String(50), default="new") # new, acknowledged, reviewed, false_positive, resolved, escalated
    review_required = Column(Boolean, default=False)
    provider_name = Column(String(100))
    model_version = Column(String(100))
    prompt_version = Column(String(100))
    occurred_at = Column(DateTime, nullable=False, server_default=func.now())
    evidence_path = Column(Text)
    metadata_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CCTVAnalysisJob(Base):
    __tablename__ = "cctv_analysis_jobs"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    camera_id = Column(Integer, ForeignKey("cctv_cameras.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(String(50), nullable=False) # clip_analysis, snapshot_analysis
    status = Column(String(50), default="pending") # pending, processing, completed, failed
    video_path = Column(Text)
    source_filename = Column(String(255))
    source_mime_type = Column(String(100))
    source_size_bytes = Column(Integer)
    source_checksum = Column(String(128))
    source_blob = Column(LargeBinary)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    provider_name = Column(String(100))
    model_version = Column(String(100))
    prompt_version = Column(String(100))
    evidence_filename = Column(String(255))
    evidence_mime_type = Column(String(100))
    evidence_size_bytes = Column(Integer)
    evidence_checksum = Column(String(128))
    evidence_blob = Column(LargeBinary)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CCTVMetricHourly(Base):
    __tablename__ = "cctv_metrics_hourly"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False)
    camera_id = Column(Integer, ForeignKey("cctv_cameras.id", ondelete="CASCADE"), nullable=False)
    metric_date = Column(Date, nullable=False)
    hour = Column(Integer, nullable=False)
    metric_key = Column(String(100), nullable=False)
    metric_value = Column(Numeric(12, 4), default=0)
    confidence = Column(Numeric(4, 2))
    provider_name = Column(String(100))
    model_version = Column(String(100))
    prompt_version = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())


class CCTVReviewAction(Base):
    __tablename__ = "cctv_review_actions"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    event_id = Column(Integer, ForeignKey("cctv_events.id", ondelete="CASCADE"), nullable=False)
    reviewer_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(String(50), nullable=False) # acknowledge, resolve, mark_false_positive, escalate
    from_status = Column(String(50))
    to_status = Column(String(50))
    comment = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "integration_type", "provider", name="uq_integrations_type_provider"),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    integration_type = Column(String(50), nullable=False) # pos, pump, loyalty, inventory
    provider = Column(String(100), nullable=False)
    display_name = Column(String(255))
    status = Column(String(32), default="active")
    config_json = Column(JSONB)
    metadata_json = Column(JSONB)
    secret_ref = Column(String(255))
    secret_refs_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class IntegrationStationMapping(Base):
    __tablename__ = "integration_station_mappings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "integration_id",
            "station_id",
            name="uq_integration_station_mapping_station",
        ),
        UniqueConstraint(
            "tenant_id",
            "integration_id",
            "external_station_id",
            name="uq_integration_station_mapping_external_station",
        ),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    integration_id = Column(
        Integer, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
    )
    station_id = Column(
        Integer, ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    external_station_id = Column(String(255), nullable=False)
    external_location_id = Column(String(255))
    metadata_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    integration_id = Column(
        Integer, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
    )
    external_id = Column(String(255))
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    event_type = Column(String(100), nullable=False) # sale, fueling_start, fueling_end, stock_update
    occurred_at = Column(DateTime, nullable=False)
    payload_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())


class IntegrationImportBatch(Base):
    __tablename__ = "integration_import_batches"

    id = Column(Integer, Identity(always=False), primary_key=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    integration_id = Column(
        Integer, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
    )
    import_type = Column(String(50), nullable=False, default="csv_placeholder")
    status = Column(String(32), default="pending")
    source_filename = Column(String(255))
    source_mime_type = Column(String(100))
    source_size_bytes = Column(Integer)
    source_checksum = Column(String(128))
    source_blob = Column(LargeBinary)
    metadata_json = Column(JSONB)
    result_json = Column(JSONB)
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


Tenant.subscription = relationship(
    "TenantSubscription", back_populates="tenant", cascade="all, delete-orphan", uselist=False
)
Tenant.settings = relationship(
    "TenantSetting", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.feature_flags = relationship(
    "TenantFeatureFlag", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.regions = relationship(
    "Region", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.station_categories = relationship(
    "StationCategory", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.stations = relationship(
    "Station", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.users = relationship(
    "User", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.sessions = relationship(
    "SessionToken", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.activity_logs = relationship(
    "ActivityLog", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.submissions = relationship(
    "Submission", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.ai_alerts = relationship(
    "AIAlert", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.ai_reports = relationship(
    "AIReport", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.ai_jobs = relationship(
    "AIJob", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.scheduled_reports = relationship(
    "ScheduledReport", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.report_schedules = relationship(
    "ReportSchedule", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.report_subscriptions = relationship(
    "ReportSubscription", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.report_delivery_attempts = relationship(
    "ReportDeliveryAttempt", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.ai_inference_latency = relationship(
    "AIInferenceLatency", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.cctv_cameras = relationship(
    "CCTVCamera", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.cctv_zones = relationship(
    "CCTVZone", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.cctv_events = relationship(
    "CCTVEvent", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.cctv_review_actions = relationship(
    "CCTVReviewAction", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.cctv_analysis_jobs = relationship(
    "CCTVAnalysisJob", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.cctv_metrics_hourly = relationship(
    "CCTVMetricHourly", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.integrations = relationship(
    "Integration", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.integration_station_mappings = relationship(
    "IntegrationStationMapping", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.integration_events = relationship(
    "IntegrationEvent", back_populates="tenant", cascade="all, delete-orphan"
)
Tenant.integration_import_batches = relationship(
    "IntegrationImportBatch", back_populates="tenant", cascade="all, delete-orphan"
)

CCTVCamera.tenant = relationship("Tenant", back_populates="cctv_cameras")
CCTVCamera.station = relationship("Station", back_populates="cameras")
CCTVCamera.zones = relationship("CCTVZone", back_populates="camera", cascade="all, delete-orphan")
CCTVCamera.jobs = relationship("CCTVAnalysisJob", back_populates="camera", cascade="all, delete-orphan")

CCTVZone.tenant = relationship("Tenant", back_populates="cctv_zones")
CCTVZone.camera = relationship("CCTVCamera", back_populates="zones")

CCTVEvent.tenant = relationship("Tenant", back_populates="cctv_events")
CCTVEvent.station = relationship("Station", back_populates="cctv_events")
CCTVEvent.job = relationship("CCTVAnalysisJob", back_populates="events")
CCTVEvent.camera = relationship("CCTVCamera")
CCTVEvent.zone = relationship("CCTVZone")
CCTVEvent.review_actions = relationship("CCTVReviewAction", back_populates="event", cascade="all, delete-orphan")

CCTVReviewAction.tenant = relationship("Tenant", back_populates="cctv_review_actions")
CCTVReviewAction.event = relationship("CCTVEvent", back_populates="review_actions")
CCTVReviewAction.reviewer = relationship("User")

CCTVAnalysisJob.tenant = relationship("Tenant", back_populates="cctv_analysis_jobs")
CCTVAnalysisJob.camera = relationship("CCTVCamera", back_populates="jobs")
CCTVAnalysisJob.events = relationship("CCTVEvent", back_populates="job")

CCTVMetricHourly.tenant = relationship("Tenant", back_populates="cctv_metrics_hourly")
CCTVMetricHourly.station = relationship("Station")
CCTVMetricHourly.camera = relationship("CCTVCamera")

Integration.tenant = relationship("Tenant", back_populates="integrations")
Integration.station_mappings = relationship(
    "IntegrationStationMapping", back_populates="integration", cascade="all, delete-orphan"
)
Integration.events = relationship("IntegrationEvent", back_populates="integration", cascade="all, delete-orphan")
Integration.import_batches = relationship(
    "IntegrationImportBatch", back_populates="integration", cascade="all, delete-orphan"
)

IntegrationStationMapping.tenant = relationship("Tenant", back_populates="integration_station_mappings")
IntegrationStationMapping.integration = relationship("Integration", back_populates="station_mappings")
IntegrationStationMapping.station = relationship("Station", back_populates="integration_station_mappings")

IntegrationEvent.tenant = relationship("Tenant", back_populates="integration_events")
IntegrationEvent.integration = relationship("Integration", back_populates="events")
IntegrationEvent.station = relationship("Station", back_populates="integration_events")

IntegrationImportBatch.tenant = relationship("Tenant", back_populates="integration_import_batches")
IntegrationImportBatch.integration = relationship("Integration", back_populates="import_batches")

TenantSubscription.tenant = relationship("Tenant", back_populates="subscription")
TenantSetting.tenant = relationship("Tenant", back_populates="settings")
TenantFeatureFlag.tenant = relationship("Tenant", back_populates="feature_flags")

Region.tenant = relationship("Tenant", back_populates="regions")
Region.stations = relationship(
    "Station", back_populates="region", cascade="all, delete-orphan"
)
Region.users = relationship(
    "User", back_populates="region", cascade="all, delete-orphan"
)
Region.ai_reports = relationship("AIReport", back_populates="region")

StationCategory.tenant = relationship("Tenant", back_populates="station_categories")
StationCategory.stations = relationship(
    "Station", back_populates="category", cascade="all, delete-orphan"
)

Station.tenant = relationship("Tenant", back_populates="stations")
Station.region = relationship("Region", back_populates="stations")
Station.category = relationship("StationCategory", back_populates="stations")
Station.users = relationship("User", back_populates="station", cascade="all, delete-orphan")
Station.submissions = relationship(
    "Submission", back_populates="station", cascade="all, delete-orphan"
)
Station.cameras = relationship("CCTVCamera", back_populates="station", cascade="all, delete-orphan")
Station.cctv_events = relationship(
    "CCTVEvent", back_populates="station", cascade="all, delete-orphan"
)
Station.integration_events = relationship(
    "IntegrationEvent", back_populates="station", cascade="all, delete-orphan"
)
Station.integration_station_mappings = relationship(
    "IntegrationStationMapping", back_populates="station", cascade="all, delete-orphan"
)
Station.alerts = relationship("AIAlert", back_populates="station", cascade="all, delete-orphan")
Station.ai_reports = relationship("AIReport", back_populates="station")

User.tenant = relationship("Tenant", back_populates="users")
User.region = relationship("Region", back_populates="users")
User.station = relationship("Station", back_populates="users")
User.submissions = relationship(
    "Submission", back_populates="user", cascade="all, delete-orphan"
)
User.manager = relationship("User", remote_side=[User.id], back_populates="direct_reports")
User.direct_reports = relationship("User", back_populates="manager")
User.scheduled_reports = relationship(
    "ScheduledReport", back_populates="recipient", cascade="all, delete-orphan"
)
User.report_subscriptions = relationship(
    "ReportSubscription", back_populates="recipient", cascade="all, delete-orphan"
)
User.report_delivery_attempts = relationship(
    "ReportDeliveryAttempt", back_populates="recipient", cascade="all, delete-orphan"
)
User.sessions = relationship(
    "SessionToken", back_populates="user", cascade="all, delete-orphan"
)

SessionToken.tenant = relationship("Tenant", back_populates="sessions")
SessionToken.user = relationship("User", back_populates="sessions")

ActivityLog.tenant = relationship("Tenant", back_populates="activity_logs")

Submission.tenant = relationship("Tenant", back_populates="submissions")
Submission.station = relationship("Station", back_populates="submissions")
Submission.user = relationship("User", back_populates="submissions")
Submission.inference_latency = relationship(
    "AIInferenceLatency", back_populates="submission", cascade="all, delete-orphan"
)

AIInferenceLatency.tenant = relationship("Tenant", back_populates="ai_inference_latency")
AIInferenceLatency.submission = relationship(
    "Submission", back_populates="inference_latency"
)

AIAlert.tenant = relationship("Tenant", back_populates="ai_alerts")
AIAlert.station = relationship("Station", back_populates="alerts")

ScheduledReport.tenant = relationship("Tenant", back_populates="scheduled_reports")
ScheduledReport.recipient = relationship("User", back_populates="scheduled_reports")
ScheduledReport.delivery_attempts = relationship(
    "ReportDeliveryAttempt", back_populates="scheduled_report"
)

ReportSchedule.tenant = relationship("Tenant", back_populates="report_schedules")
ReportSchedule.subscriptions = relationship(
    "ReportSubscription", back_populates="schedule", cascade="all, delete-orphan"
)
ReportSchedule.delivery_attempts = relationship(
    "ReportDeliveryAttempt", back_populates="report_schedule"
)

ReportSubscription.tenant = relationship("Tenant", back_populates="report_subscriptions")
ReportSubscription.schedule = relationship("ReportSchedule", back_populates="subscriptions")
ReportSubscription.recipient = relationship("User", back_populates="report_subscriptions")
ReportSubscription.delivery_attempts = relationship(
    "ReportDeliveryAttempt", back_populates="report_subscription"
)

ReportDeliveryAttempt.tenant = relationship("Tenant", back_populates="report_delivery_attempts")
ReportDeliveryAttempt.scheduled_report = relationship(
    "ScheduledReport", back_populates="delivery_attempts"
)
ReportDeliveryAttempt.report_schedule = relationship(
    "ReportSchedule", back_populates="delivery_attempts"
)
ReportDeliveryAttempt.report_subscription = relationship(
    "ReportSubscription", back_populates="delivery_attempts"
)
ReportDeliveryAttempt.recipient = relationship("User", back_populates="report_delivery_attempts")

AIJob.tenant = relationship("Tenant", back_populates="ai_jobs")

AIReport.tenant = relationship("Tenant", back_populates="ai_reports")
AIReport.region = relationship("Region", back_populates="ai_reports")
AIReport.station = relationship("Station", back_populates="ai_reports")
