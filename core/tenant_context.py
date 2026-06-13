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


def get_current_tenant_context() -> Optional[TenantContext]:
    return _CURRENT_TENANT_CONTEXT.get()


def set_current_tenant_context(context: Optional[TenantContext]) -> None:
    _CURRENT_TENANT_CONTEXT.set(context)


def clear_current_tenant_context() -> None:
    _CURRENT_TENANT_CONTEXT.set(None)


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
    token = _CURRENT_TENANT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_TENANT_CONTEXT.reset(token)


@contextmanager
def platform_context() -> Iterator[TenantContext]:
    token = _CURRENT_TENANT_CONTEXT.set(
        TenantContext(tenant_id=-1, platform_access=True)
    )
    try:
        yield _CURRENT_TENANT_CONTEXT.get()
    finally:
        _CURRENT_TENANT_CONTEXT.reset(token)
