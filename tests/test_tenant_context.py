import pytest

from core.tenant_context import (
    TenantContext,
    TenantContextError,
    clear_current_tenant_context,
    current_tenant_id,
    get_current_tenant_context,
    platform_context,
    tenant_context,
)


def test_tenant_context_sets_and_restores_current_context() -> None:
    clear_current_tenant_context()
    context = TenantContext(tenant_id=7, user_id=11, role="General Manager")

    with tenant_context(context):
        assert get_current_tenant_context() == context
        assert current_tenant_id() == 7

    assert get_current_tenant_context() is None


def test_current_tenant_id_fails_closed_without_context() -> None:
    clear_current_tenant_context()
    with pytest.raises(TenantContextError):
        current_tenant_id()


def test_platform_context_marks_platform_access() -> None:
    clear_current_tenant_context()
    with platform_context() as context:
        assert context is not None
        assert context.platform_access is True
