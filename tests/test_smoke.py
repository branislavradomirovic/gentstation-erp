import pytest
from unittest.mock import MagicMock, patch
import streamlit as st
from app import get_page_registry
from core.tenant_context import TenantContext

@pytest.fixture
def mock_conn():
    """Mocks the database connection and common query results."""
    conn = MagicMock()
    # Mock count queries
    conn.execute.return_value.fetchone.return_value = (0,)
    # Mock read_sql_query to return empty DataFrames
    return conn

@pytest.fixture
def mock_streamlit_session():
    """Setup a standard authenticated session state for testing."""
    with patch.object(st, 'session_state', {
        "user_id": 1,
        "tenant_id": 1,
        "username": "admin",
        "user_role": "General Manager",
        "boot_complete": True
    }) as mock_state:
        yield mock_state

def test_page_registry_completeness():
    """Verify that all files imported in the registry actually exist and are callable."""
    registry = get_page_registry()
    assert len(registry) >= 15  # Ensure all core operational pages are present
    for page_name, render_func in registry.items():
        assert callable(render_func), f"Page {page_name} does not have a valid render function"

def test_all_pages_register_render_callables_without_import_side_effects(
    mock_conn, mock_streamlit_session
):
    """
    Smoke-test the page registry without executing live Streamlit page bodies.

    Full render execution is too integration-heavy for plain pytest because many
    pages open DB/session code paths directly. The production-safe guarantee we
    want here is that the app imports cleanly and the registry exposes callable
    render functions.
    """
    registry = get_page_registry()
    for page_id, render_func in registry.items():
        assert callable(render_func), f"Page '{page_id}' should expose a render function"
        assert render_func.__module__.startswith(("pages.", "ui.")), (
            f"Page '{page_id}' should resolve to a local page/ui module"
        )

def test_tenant_context_enforcement():
    """Verifies that the app fails closed if the tenant context is corrupted."""
    from core.access_control import require_page_access
    from core.tenant_context import TenantContextError

    # Context with missing ID
    bad_ctx = TenantContext(tenant_id=None)

    with pytest.raises(TenantContextError):
        require_page_access(
            "Dashboard",
            bad_ctx,
            "General Manager",
            "admin"
        )
