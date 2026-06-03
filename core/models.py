from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Numeric,
    JSON,
    func,
    Identity,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Region(Base):
    __tablename__ = "regions"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class StationCategory(Base):
    __tablename__ = "station_categories"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    color = Column(String(50), nullable=False, default="#808080")
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class Station(Base):
    __tablename__ = "stations"
    id = Column(Integer, Identity(always=False), primary_key=True)
    name = Column(String(255), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"))
    physical_address = Column(Text)
    email = Column(String(255))
    lat = Column(Numeric(10, 8))
    lon = Column(Numeric(11, 8))
    category_id = Column(Integer, ForeignKey("station_categories.id", ondelete="CASCADE"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, Identity(always=False), primary_key=True)
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

class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, Identity(always=False), primary_key=True)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    employee_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    video_path = Column(Text)
    audio_path = Column(Text)
    role = Column(String(100))
    timestamp = Column(DateTime, server_default=func.now())
    processed = Column(Integer, default=0)
    status = Column(String(50), default='pending')
    processing_started_ts = Column(DateTime)
    retry_count = Column(Integer, default=0)
    processed_ts = Column(DateTime)
    data_json = Column(JSON)
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
    timestamp = Column(DateTime, server_default=func.now())
    model_name = Column(String(255))
    latency_seconds = Column(Numeric(10, 2))
    submission_id = Column(Integer, ForeignKey("submissions.id", ondelete="CASCADE"))

class AIAlert(Base):
    __tablename__ = "ai_alerts"
    id = Column(Integer, Identity(always=False), primary_key=True)
    station_id = Column(Integer, ForeignKey("stations.id", ondelete="CASCADE"))
    severity = Column(String(50))
    message = Column(Text)
    status = Column(String(50), default='new')
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
    report_type = Column(String(32), nullable=False)
    scope_type = Column(String(32), nullable=False)
    scope_id = Column(Integer)
    recipient_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    delivery_channel = Column(String(32))
    payload_json = Column(JSON)
    error_message = Column(Text)
    sent_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    recipient = relationship("User", back_populates="scheduled_reports")


# Define relationships after all dependent classes exist so mapper
# configuration is resilient during Streamlit reloads.
Region.stations = relationship("Station", back_populates="region", cascade="all, delete-orphan")
Station.region = relationship("Region", back_populates="stations")
Station.users = relationship("User", back_populates="station", cascade="all, delete-orphan")
Station.submissions = relationship("Submission", back_populates="station", cascade="all, delete-orphan")
Region.users = relationship("User", back_populates="region", cascade="all, delete-orphan")
User.region = relationship("Region", back_populates="users")
User.station = relationship("Station", back_populates="users")
User.submissions = relationship("Submission", back_populates="user", cascade="all, delete-orphan")
User.manager = relationship("User", remote_side=[User.id], back_populates="direct_reports")
User.direct_reports = relationship("User", back_populates="manager")
Submission.station = relationship("Station", back_populates="submissions")
Submission.user = relationship("User", back_populates="submissions")
StationCategory.stations = relationship("Station", back_populates="category", cascade="all, delete-orphan")
Station.category = relationship("StationCategory", back_populates="stations")
Station.alerts = relationship("AIAlert", back_populates="station", cascade="all, delete-orphan")
AIAlert.station = relationship("Station", back_populates="alerts")
User.scheduled_reports = relationship("ScheduledReport", back_populates="recipient", cascade="all, delete-orphan")
