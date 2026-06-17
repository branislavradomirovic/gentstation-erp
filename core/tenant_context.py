from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional


class TenantContextError(RuntimeError):
    """Raised when tenant-scoped operations are attempted without context."""


@dataclass(frozen=True)
class TenantContext:
    tenant_id: int
    user_id: Optional[int] = None
    role: Optional[str] = None
    username: Optional[str] = None
    station_id: Optional[int] = None
    region_id: Optional[int] = None
    platform_access: bool = False


_CURRENT_TENANT_CONTEXT: ContextVar[Optional[TenantContext]] = ContextVar(
    "current_tenant_context", default=None
)


def _session_state_tenant_context() -> Optional[TenantContext]:
    try:
        import streamlit as st  # Lazy import so non-UI code stays lightweight.
    except Exception:
        return None

    session_state = getattr(st, "session_state", None)
    if not session_state:
        return None

    current = session_state.get("current_tenant_context")
    if isinstance(current, TenantContext):
        return current

    tenant_id = session_state.get("tenant_id")
    if tenant_id is None:
        return None

    try:
        tenant_id_value = int(tenant_id)
    except (TypeError, ValueError):
        return None

    return TenantContext(
        tenant_id=tenant_id_value,
        user_id=session_state.get("user_id"),
        role=session_state.get("user_role"),
        username=session_state.get("username"),
        station_id=session_state.get("user_station_id"),
        region_id=session_state.get("user_region_id"),
        platform_access=bool(session_state.get("platform_access", False)),
    )


def get_current_tenant_context() -> Optional[TenantContext]:
    context = _CURRENT_TENANT_CONTEXT.get()
    if context is not None:
        return context
    return _session_state_tenant_context()


def set_current_tenant_context(context: Optional[TenantContext]) -> None:
    _CURRENT_TENANT_CONTEXT.set(context)
    try:
        import streamlit as st

        if context is None:
            st.session_state.pop("current_tenant_context", None)
            for key in (
                "tenant_id",
                "user_id",
                "user_role",
                "username",
                "user_station_id",
                "user_region_id",
                "platform_access",
            ):
                st.session_state.pop(key, None)
        else:
            st.session_state["current_tenant_context"] = context
            st.session_state["tenant_id"] = context.tenant_id
            if context.user_id is not None:
                st.session_state["user_id"] = context.user_id
            if context.role is not None:
                st.session_state["user_role"] = context.role
            if context.username is not None:
                st.session_state["username"] = context.username
            if context.station_id is not None:
                st.session_state["user_station_id"] = context.station_id
            if context.region_id is not None:
                st.session_state["user_region_id"] = context.region_id
            st.session_state["platform_access"] = context.platform_access
    except Exception:
        pass


def clear_current_tenant_context() -> None:
    _CURRENT_TENANT_CONTEXT.set(None)
    try:
        import streamlit as st

        set_current_tenant_context(None)
    except Exception:
        pass


def require_current_tenant_context() -> TenantContext:
    context = get_current_tenant_context()
    if context is None or context.tenant_id is None:
        raise TenantContextError(
            "Tenant context is required for this operation and was not provided."
        )
    return context


def current_tenant_id() -> int:
    return require_current_tenant_context().tenant_id


def has_platform_access() -> bool:
    context = get_current_tenant_context()
    return bool(context and context.platform_access)


@contextmanager
def tenant_context(context: TenantContext) -> Iterator[TenantContext]:
    previous_context = get_current_tenant_context()
    set_current_tenant_context(context)
    try:
        yield context
    finally:
        set_current_tenant_context(previous_context)


@contextmanager
def platform_context() -> Iterator[TenantContext]:
    previous_context = get_current_tenant_context()
    context = TenantContext(tenant_id=-1, platform_access=True)
    set_current_tenant_context(context)
    try:
        yield context
    finally:
        set_current_tenant_context(previous_context)
