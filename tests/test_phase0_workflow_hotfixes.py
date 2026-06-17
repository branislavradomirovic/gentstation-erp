import importlib
from types import SimpleNamespace

import core.comm_service as comm_service
import core.platform_admin as platform_admin


class FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class ResetConnection:
    def __init__(self, *, user_row, last_request=None):
        self.user_row = user_row
        self.last_request = last_request
        self.executed = []
        self.commits = 0

    def execute(self, query, params=()):
        self.executed.append((" ".join(query.split()), params))
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT id, username, role, tenant_id, password_hash, force_password_change FROM users"):
            return FakeResult(self.user_row)
        if normalized.startswith("SELECT timestamp FROM activity_logs"):
            return FakeResult(self.last_request)
        return FakeResult(None)

    def commit(self):
        self.commits += 1


class ActivationConnection:
    def __init__(self, user_row):
        self.user_row = user_row

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT id, username, email, role, is_active, station_id, region_id, name, surname FROM users"):
            return FakeResult(self.user_row)
        return FakeResult(None)

    def commit(self):
        return None


class SMTPRecorder:
    sent_messages = []
    should_fail = False

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        return None

    def login(self, user, password):
        self.user = user
        self.password = password

    def send_message(self, msg):
        if self.should_fail:
            raise RuntimeError("smtp send failed")
        self.sent_messages.append(msg)


def reload_runtime_config():
    import core.runtime_config as runtime_config

    return importlib.reload(runtime_config)


def _capture_streamlit_messages(monkeypatch):
    captured = {"success": [], "error": [], "warning": []}
    monkeypatch.setattr(comm_service.st, "success", lambda message: captured["success"].append(message))
    monkeypatch.setattr(comm_service.st, "error", lambda message: captured["error"].append(message))
    monkeypatch.setattr(comm_service.st, "warning", lambda message: captured["warning"].append(message))
    return captured


def test_configured_app_login_url_prefers_app_login_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setenv("APP_LOGIN_URL", "https://preprod.example.com")
    monkeypatch.setenv("APP_BASE_URL", "https://base.example.com")

    runtime_config = reload_runtime_config()

    assert runtime_config.configured_app_login_url() == "https://preprod.example.com/"


def test_configured_app_login_url_falls_back_to_app_base_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("APP_LOGIN_URL", raising=False)
    monkeypatch.setenv("APP_BASE_URL", "https://staging.example.com")

    runtime_config = reload_runtime_config()

    assert runtime_config.configured_app_login_url() == "https://staging.example.com/"


def test_configured_app_login_url_requires_explicit_value_for_preprod(monkeypatch):
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.delenv("APP_LOGIN_URL", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)

    runtime_config = reload_runtime_config()

    try:
        runtime_config.configured_app_login_url()
        assert False, "Expected a RuntimeError when APP_LOGIN_URL is missing in preprod."
    except RuntimeError as exc:
        assert "APP_LOGIN_URL or APP_BASE_URL must be configured" in str(exc)


def test_send_password_reset_succeeds_when_audit_logging_fails(monkeypatch):
    captured = _capture_streamlit_messages(monkeypatch)
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setenv("APP_LOGIN_URL", "https://pilot.example.com")
    monkeypatch.setenv("SMTP_USER", "ops@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setattr(comm_service.smtplib, "SMTP", SMTPRecorder)
    monkeypatch.setattr(comm_service, "log_activity", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit offline")))

    SMTPRecorder.sent_messages = []
    SMTPRecorder.should_fail = False
    conn = ResetConnection(
        user_row=(10, "alice", "Employee", 77, "old-hash", False),
    )

    ok, message = comm_service.send_password_reset_email(conn, "alice@example.com")

    assert ok is True
    assert message == "Temporary password email sent."
    assert conn.commits == 1
    assert len(SMTPRecorder.sent_messages) == 1
    assert captured["error"] == []
    assert captured["success"] == [
        "Temporary password sent. Please check your email and sign in with it before changing your password."
    ]


def test_send_password_reset_stops_before_updating_when_login_url_is_missing(monkeypatch):
    captured = _capture_streamlit_messages(monkeypatch)
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.delenv("APP_LOGIN_URL", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("RENDER_SERVICE_ID", raising=False)
    monkeypatch.setenv("SMTP_USER", "ops@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setattr(comm_service.smtplib, "SMTP", SMTPRecorder)

    conn = ResetConnection(
        user_row=(20, "carol", "Employee", 88, "old-hash", False),
    )

    ok, message = comm_service.send_password_reset_email(conn, "carol@example.com")

    assert ok is False
    assert "APP_LOGIN_URL or APP_BASE_URL must be configured" in message
    assert conn.commits == 0
    assert captured["success"] == []
    assert len(captured["error"]) == 1


def test_send_password_reset_restores_existing_password_when_email_fails(monkeypatch):
    captured = _capture_streamlit_messages(monkeypatch)
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setenv("APP_LOGIN_URL", "https://pilot.example.com")
    monkeypatch.setenv("SMTP_USER", "ops@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setattr(comm_service.smtplib, "SMTP", SMTPRecorder)
    monkeypatch.setattr(comm_service, "log_activity", lambda *args, **kwargs: None)

    SMTPRecorder.sent_messages = []
    SMTPRecorder.should_fail = True
    conn = ResetConnection(
        user_row=(15, "bob", "General Manager", 91, "old-hash-value", True),
    )

    ok, message = comm_service.send_password_reset_email(conn, "bob@example.com")

    assert ok is False
    assert "Failed to send temporary password email" in message
    assert conn.commits == 2
    restore_query, restore_params = conn.executed[-1]
    assert "SET password_hash = %s, force_password_change = %s" in restore_query
    assert restore_params == ("old-hash-value", True, 91, 15)
    assert captured["success"] == []
    assert len(captured["error"]) == 1


def test_send_activation_email_supports_explicit_tenant_id(monkeypatch):
    monkeypatch.setenv("APP_ENV", "preprod")
    monkeypatch.setenv("APP_LOGIN_URL", "https://tenant.example.com")
    monkeypatch.setenv("SMTP_USER", "ops@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setattr(comm_service.smtplib, "SMTP", SMTPRecorder)
    monkeypatch.setattr(
        comm_service,
        "require_current_tenant_context",
        lambda: (_ for _ in ()).throw(AssertionError("tenant context should not be required")),
    )
    activity = {}

    def fake_log_activity(conn, action, details, tenant_id=None):
        activity["action"] = action
        activity["tenant_id"] = tenant_id
        activity["details"] = details

    monkeypatch.setattr(comm_service, "log_activity", fake_log_activity)
    SMTPRecorder.sent_messages = []
    SMTPRecorder.should_fail = False
    conn = ActivationConnection(
        (3, "gm.user", "gm@example.com", "General Manager", True, None, None, "GM", "User")
    )

    ok, message = comm_service.send_activation_email(conn, 3, tenant_id=17)

    assert ok is True
    assert "Activation email sent" in message
    assert activity["action"] == "SEND_ACTIVATION_EMAIL"
    assert activity["tenant_id"] == 17


def test_create_company_admin_delegates_to_create_user(monkeypatch):
    captured = {}

    def fake_create_user(**kwargs):
        captured.update(kwargs)
        return {"id": 5, "username": kwargs["username"], "email": kwargs["email"]}

    monkeypatch.setattr(platform_admin, "create_user", fake_create_user)
    monkeypatch.setattr(platform_admin, "_user_exists", lambda conn, username, email: False)

    user = platform_admin.create_company_admin(
        conn=SimpleNamespace(),
        tenant_id=44,
        username="company.admin",
        password="temp1234",  # pragma: allowlist secret
        email="admin@company.test",
        first_name="Company",
        surname="Admin",
    )

    assert user["id"] == 5
    assert captured["tenant_id"] == 44
    assert captured["role"] == "General Manager"
    assert captured["password"] == "temp1234"  # pragma: allowlist secret
