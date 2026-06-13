from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
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
    telegram_chat_id = Column(String(255))
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
    audio_path = Column(Text)
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
Tenant.ai_inference_latency = relationship(
    "AIInferenceLatency", back_populates="tenant", cascade="all, delete-orphan"
)

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

AIJob.tenant = relationship("Tenant", back_populates="ai_jobs")

AIReport.tenant = relationship("Tenant", back_populates="ai_reports")
AIReport.region = relationship("Region", back_populates="ai_reports")
AIReport.station = relationship("Station", back_populates="ai_reports")
