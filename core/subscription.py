from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Dict

from core.tenant_context import (
    TenantContext,
    TenantContextError,
    require_current_tenant_context,
)

TIER_1_AI_DAILY_OPERATIONS = "tier_1_ai_daily_operations"
TIER_2_CCTV_INTELLIGENCE = "tier_2_cctv_intelligence"

FEATURE_AI_DAILY_OPERATIONS = TIER_1_AI_DAILY_OPERATIONS
FEATURE_CCTV_INTELLIGENCE = TIER_2_CCTV_INTELLIGENCE
FEATURE_TELEGRAM_INTAKE = "telegram_intake"
FEATURE_EMAIL_NOTIFICATIONS = "email_notifications"
FEATURE_REPORT_SCHEDULER = "report_scheduler"

RESOURCE_STATIONS = "stations"
RESOURCE_EMPLOYEES = "employees"
RESOURCE_CAMERAS = "cameras"


class FeatureGateError(PermissionError):
    """Raised when a tenant attempts to access a gated feature."""


class UsageLimitError(RuntimeError):
    """Raised when a tenant exceeds a plan usage limit."""


@dataclass(frozen=True)
class TierDefinition:
    code: str
    rank: int
    label: str
    description: str
    feature_keys: frozenset[str]
    default_limits: Dict[str, Optional[int]]


@dataclass(frozen=True)
class FeatureDefinition:
    key: str
    label: str
    description: str
    minimum_tier: str


@dataclass(frozen=True)
class SubscriptionSnapshot:
    tenant_id: int
    tier_code: str
    status: str
    billing_cycle: Optional[str]
    billing_currency: Optional[str]
    limits: Dict[str, Optional[int]]
    feature_overrides: dict[str, bool] = field(default_factory=dict)


TIER_DEFINITIONS: dict[str, TierDefinition] = {
    TIER_1_AI_DAILY_OPERATIONS: TierDefinition(
        code=TIER_1_AI_DAILY_OPERATIONS,
        rank=1,
        label="Tier 1 - AI Daily Operations",
        description="Daily station operations, Telegram intake, AI reports, alerts, and scheduler workflows.",
        feature_keys=frozenset(
            {
                FEATURE_AI_DAILY_OPERATIONS,
                FEATURE_TELEGRAM_INTAKE,
                FEATURE_EMAIL_NOTIFICATIONS,
                FEATURE_REPORT_SCHEDULER,
            }
        ),
        default_limits={
            RESOURCE_STATIONS: None,
            RESOURCE_EMPLOYEES: None,
            RESOURCE_CAMERAS: 0,
        },
    ),
    TIER_2_CCTV_INTELLIGENCE: TierDefinition(
        code=TIER_2_CCTV_INTELLIGENCE,
        rank=2,
        label="Tier 2 - CCTV Intelligence",
        description="Everything in Tier 1 plus CCTV intelligence workflows, camera capacity, and future CCTV routes.",
        feature_keys=frozenset(
            {
                FEATURE_AI_DAILY_OPERATIONS,
                FEATURE_CCTV_INTELLIGENCE,
                FEATURE_TELEGRAM_INTAKE,
                FEATURE_EMAIL_NOTIFICATIONS,
                FEATURE_REPORT_SCHEDULER,
            }
        ),
        default_limits={
            RESOURCE_STATIONS: None,
            RESOURCE_EMPLOYEES: None,
            RESOURCE_CAMERAS: None,
        },
    ),
}


FEATURE_DEFINITIONS: dict[str, FeatureDefinition] = {
    FEATURE_AI_DAILY_OPERATIONS: FeatureDefinition(
        key=FEATURE_AI_DAILY_OPERATIONS,
        label="AI Daily Operations",
        description="Operational video intake, report generation, alerts, and daily review flows.",
        minimum_tier=TIER_1_AI_DAILY_OPERATIONS,
    ),
    FEATURE_CCTV_INTELLIGENCE: FeatureDefinition(
        key=FEATURE_CCTV_INTELLIGENCE,
        label="CCTV Intelligence",
        description="CCTV-specific intelligence routes, workers, and camera-aware workflows.",
        minimum_tier=TIER_2_CCTV_INTELLIGENCE,
    ),
    FEATURE_TELEGRAM_INTAKE: FeatureDefinition(
        key=FEATURE_TELEGRAM_INTAKE,
        label="Telegram Intake",
        description="Telegram bot ingestion for station submissions.",
        minimum_tier=TIER_1_AI_DAILY_OPERATIONS,
    ),
    FEATURE_EMAIL_NOTIFICATIONS: FeatureDefinition(
        key=FEATURE_EMAIL_NOTIFICATIONS,
        label="Email Notifications",
        description="Scheduled and event-based email delivery.",
        minimum_tier=TIER_1_AI_DAILY_OPERATIONS,
    ),
    FEATURE_REPORT_SCHEDULER: FeatureDefinition(
        key=FEATURE_REPORT_SCHEDULER,
        label="Report Scheduler",
        description="Automated regional and company reporting.",
        minimum_tier=TIER_1_AI_DAILY_OPERATIONS,
    ),
}


def _normalize_tier_code(tier_code: Optional[str]) -> str:
    if tier_code in TIER_DEFINITIONS:
        return str(tier_code)
    return TIER_1_AI_DAILY_OPERATIONS


def get_tier_definition(tier_code: Optional[str]) -> TierDefinition:
    return TIER_DEFINITIONS[_normalize_tier_code(tier_code)]


def is_tier_at_least(current_tier: Optional[str], minimum_tier: str) -> bool:
    current = get_tier_definition(current_tier)
    required = get_tier_definition(minimum_tier)
    return current.rank >= required.rank


def feature_enabled_for_snapshot(
    snapshot: SubscriptionSnapshot,
    feature_key: str,
) -> bool:
    feature = FEATURE_DEFINITIONS.get(feature_key)
    if feature is None:
        return bool(snapshot.feature_overrides.get(feature_key, False))

    allowed_by_tier = is_tier_at_least(snapshot.tier_code, feature.minimum_tier)
    if not allowed_by_tier:
        return False

    override = snapshot.feature_overrides.get(feature_key)
    if override is None:
        return feature_key in get_tier_definition(snapshot.tier_code).feature_keys
    return bool(override)


def resolve_limit(snapshot: SubscriptionSnapshot, resource_key: str) -> Optional[int]:
    configured = snapshot.limits.get(resource_key)
    if configured is not None:
        return configured
    return get_tier_definition(snapshot.tier_code).default_limits.get(resource_key)


def enforce_limit_for_snapshot(
    snapshot: SubscriptionSnapshot,
    usage: dict[str, int],
    resource_key: str,
    requested: int = 1,
) -> None:
    limit_value = resolve_limit(snapshot, resource_key)
    if limit_value is None:
        return

    current_usage = int(usage.get(resource_key, 0))
    if current_usage + requested <= limit_value:
        return

    raise UsageLimitError(
        f"Plan limit reached for {resource_key}. Current usage is {current_usage}, "
        f"requested {requested}, plan limit {limit_value}."
    )


def _tenant_id_from_context(tenant_context: Optional[TenantContext] = None) -> int:
    context = tenant_context or require_current_tenant_context()
    if context.tenant_id is None:
        raise TenantContextError("Tenant context is required for subscription access.")
    return int(context.tenant_id)


def load_subscription_snapshot(
    conn,
    tenant_context: Optional[TenantContext] = None,
) -> SubscriptionSnapshot:
    tenant_id = _tenant_id_from_context(tenant_context)
    row = conn.execute(
        """
        SELECT tier_code, status, billing_cycle, billing_currency,
               station_limit, employee_limit, camera_limit
        FROM tenant_subscriptions
        WHERE tenant_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (tenant_id,),
    ).fetchone()

    feature_rows = conn.execute(
        """
        SELECT feature_key, is_enabled
        FROM tenant_feature_flags
        WHERE tenant_id = %s
        """,
        (tenant_id,),
    ).fetchall()

    if row:
        tier_code, status, billing_cycle, billing_currency, station_limit, employee_limit, camera_limit = row
    else:
        tier_code = TIER_1_AI_DAILY_OPERATIONS
        status = "provisioning"
        billing_cycle = None
        billing_currency = None
        station_limit = None
        employee_limit = None
        camera_limit = 0

    feature_overrides = {feature_key: bool(is_enabled) for feature_key, is_enabled in feature_rows}
    return SubscriptionSnapshot(
        tenant_id=tenant_id,
        tier_code=_normalize_tier_code(tier_code),
        status=status or "unknown",
        billing_cycle=billing_cycle,
        billing_currency=billing_currency,
        limits={
            RESOURCE_STATIONS: station_limit,
            RESOURCE_EMPLOYEES: employee_limit,
            RESOURCE_CAMERAS: camera_limit,
        },
        feature_overrides=feature_overrides,
    )


def load_usage_counts(conn, tenant_context: Optional[TenantContext] = None) -> dict[str, int]:
    tenant_id = _tenant_id_from_context(tenant_context)
    return {
        RESOURCE_STATIONS: int(
            conn.execute(
                "SELECT COUNT(*) FROM stations WHERE tenant_id = %s",
                (tenant_id,),
            ).fetchone()[0]
            or 0
        ),
        RESOURCE_EMPLOYEES: int(
            conn.execute(
                "SELECT COUNT(*) FROM users WHERE tenant_id = %s",
                (tenant_id,),
            ).fetchone()[0]
            or 0
        ),
        RESOURCE_CAMERAS: int(
            conn.execute(
                "SELECT COUNT(*) FROM cctv_cameras WHERE tenant_id = %s",
                (tenant_id,),
            ).fetchone()[0]
            or 0
        ),
    }


def is_feature_enabled(
    conn,
    feature_key: str,
    tenant_context: Optional[TenantContext] = None,
) -> bool:
    snapshot = load_subscription_snapshot(conn, tenant_context=tenant_context)
    return feature_enabled_for_snapshot(snapshot, feature_key)


def require_feature(
    conn,
    feature_key: str,
    tenant_context: Optional[TenantContext] = None,
    message: Optional[str] = None,
) -> None:
    if is_feature_enabled(conn, feature_key, tenant_context=tenant_context):
        return

    feature = FEATURE_DEFINITIONS.get(feature_key)
    label = feature.label if feature else feature_key
    raise FeatureGateError(message or f"{label} is not enabled for this tenant plan.")


def require_usage_capacity(
    conn,
    resource_key: str,
    requested: int = 1,
    tenant_context: Optional[TenantContext] = None,
) -> None:
    snapshot = load_subscription_snapshot(conn, tenant_context=tenant_context)
    usage = load_usage_counts(conn, tenant_context=tenant_context)
    enforce_limit_for_snapshot(snapshot, usage, resource_key, requested=requested)


def build_plan_summary(conn, tenant_context: Optional[TenantContext] = None) -> dict[str, Any]:
    snapshot = load_subscription_snapshot(conn, tenant_context=tenant_context)
    usage = load_usage_counts(conn, tenant_context=tenant_context)
    tier = get_tier_definition(snapshot.tier_code)
    features = {
        key: {
            "label": feature.label,
            "description": feature.description,
            "enabled": feature_enabled_for_snapshot(snapshot, key),
        }
        for key, feature in FEATURE_DEFINITIONS.items()
    }
    return {
        "snapshot": snapshot,
        "tier": tier,
        "usage": usage,
        "limits": {
            resource_key: resolve_limit(snapshot, resource_key)
            for resource_key in (
                RESOURCE_STATIONS,
                RESOURCE_EMPLOYEES,
                RESOURCE_CAMERAS,
            )
        },
        "features": features,
    }
