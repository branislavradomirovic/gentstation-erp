# core/auth.py
import bcrypt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from core.database import get_connection
from core.activity_logger import log_activity
from core.session import create_session_token, destroy_session_token

# Configuration
SESSION_TTL_HOURS = 8
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_DURATION_MINUTES = 15


def hash_password(plain_password: str) -> str:
    """Return bcrypt hash (utf-8 string)."""
    if isinstance(plain_password, str):
        plain_password = plain_password.encode("utf-8")
    hashed = bcrypt.hashpw(plain_password, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if isinstance(plain_password, str):
        plain_password = plain_password.encode("utf-8")
    try:
        return bcrypt.checkpw(plain_password, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_user(
    username: str,
    password: str,
    email: Optional[str],
    role: str = "Employee",
    name: Optional[str] = None,
    surname: Optional[str] = None,
    station_id: Optional[int] = None,
    region_id: Optional[int] = None,
    manager_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Create new user in users table. Returns user row dict."""
    station_scoped_roles = {
        "Employee",
        "Gas Station Supervisor",
        "Gas Station Manager",
    }
    if role in station_scoped_roles:
        if not station_id:
            raise ValueError(f"{role} requires station assignment.")
        with get_connection() as c2:
            station_row = c2.execute(
                "SELECT region_id FROM stations WHERE id = %s", (station_id,)
            ).fetchone()
        if not station_row or station_row[0] is None:
            raise ValueError("Assigned station must exist and belong to a region.")
        region_id = station_row[0]
    elif role == "Region Manager":
        if not region_id:
            raise ValueError("Region Manager requires region assignment.")
        station_id = None
    else:
        station_id = None if station_id is None else station_id

    if role == "General Manager":
        manager_user_id = None
    elif role == "Region Manager":
        if not manager_user_id:
            raise ValueError("Region Manager requires assignment to a General Manager.")
    elif role == "Gas Station Manager":
        if not manager_user_id:
            raise ValueError("Gas Station Manager requires assignment to a Region Manager.")
    elif role == "Employee":
        if not manager_user_id:
            raise ValueError("Employee requires assignment to a Gas Station Manager.")

    with get_connection() as conn:
        cur = conn.cursor()
        pw_hash = hash_password(password)
        cur.execute(
            """
            INSERT INTO users (
                username, email, password_hash, role, is_active, created_at,
                force_password_change, name, surname, station_id, region_id, manager_user_id
            )
            VALUES (%s, %s, %s, %s, TRUE, %s, TRUE, %s, %s, %s, %s, %s)
            RETURNING id
        """,
            (
                username,
                email,
                pw_hash,
                role,
                datetime.utcnow().isoformat(),
                (name or "").strip() or None,
                (surname or "").strip() or None,
                station_id,
                region_id,
                manager_user_id,
            ),
        )
        uid = cur.fetchone()[0]
        conn.commit()
        return {
            "id": uid,
            "username": username,
            "email": email,
            "role": role,
            "name": (name or "").strip() or None,
            "surname": (surname or "").strip() or None,
            "station_id": station_id,
            "region_id": region_id,
            "manager_user_id": manager_user_id,
        }


def authenticate_user(
    username_or_email: str, password: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Verify credentials with lockout logic.
    Returns (user_dict, error_message).
    """
    if not username_or_email:
        return None, "Invalid credentials"

    username_or_email = username_or_email.strip()

    with get_connection() as conn:
        cur = conn.cursor()
        # Try username (exact), then email (case-insensitive)
        cur.execute(
            """SELECT id, username, email, password_hash, role, is_active, failed_attempts, locked_until,
                      dark_mode_enabled, name, surname, station_id, region_id, telegram_chat_id,
                      force_password_change
               FROM users WHERE username = %s OR LOWER(email) = LOWER(%s)""",
            (username_or_email, username_or_email),
        )

        row = cur.fetchone()
        if not row:
            return None, "Invalid credentials"

        (
            uid,
            uname,
            uemail,
            phash,
            role,
            active,
            attempts,
            locked_until,
            dark_mode,
            fname,
            fsurname,
            sid,
            rid,
            tgid,
            force_change,
        ) = row

        # Check Maintenance Mode
        try:
            cur.execute(
                "SELECT value FROM system_settings WHERE key='maintenance_mode'"
            )
            m_row = cur.fetchone()
            if m_row and m_row[0] == "1":
                if role != "General Manager":
                    return None, "⚠️ System is in Maintenance Mode. Admin login only."
        except Exception:
            pass  # Fail open if settings table issue (schema not updated yet)

        # 1. Check if locked
        if locked_until:
            # Handle both string (from some DB drivers) and datetime objects (from psycopg2)
            if isinstance(locked_until, str):
                try:
                    lock_time = datetime.fromisoformat(locked_until)
                except ValueError:
                    lock_time = None
            else:
                lock_time = locked_until

            if lock_time and lock_time > datetime.utcnow():
                remaining_mins = (
                    int((lock_time - datetime.utcnow()).total_seconds() / 60) + 1
                )
                return None, f"Account locked. Try again in {remaining_mins} minutes."

        if not active:
            return None, "Account deactivated."

        # 2. Verify Password
        if verify_password(password, phash):
            # Success: Reset counters
            cur.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = %s",
                (uid,),
            )
            conn.commit()

            user = {
                "id": uid,
                "username": uname,
                "email": uemail,
                "role": role,
                "is_active": bool(active),
                "dark_mode": bool(dark_mode),
                "name": fname,
                "surname": fsurname,
                "station_id": sid,
                "region_id": rid,
                "telegram_chat_id": tgid,
                "force_change": bool(force_change),
            }
            return user, None
        else:
            # Failure: Increment counters
            # Only increment failed attempts if the account is not in maintenance mode
            if not (m_row and m_row[0] == "1"):
                # Only increment if not in maintenance mode
                # This prevents users from getting locked out if an admin is testing login during maintenance
                attempts = (attempts or 0) + 1
                new_lock = None
                msg = "Invalid credentials"

                if attempts >= MAX_LOGIN_ATTEMPTS:
                    new_lock = (
                        datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                    ).isoformat()
                    msg = f"Account locked due to too many failed attempts ({LOCKOUT_DURATION_MINUTES} min)."

                cur.execute(
                    "UPDATE users SET failed_attempts = %s, locked_until = %s WHERE id = %s",
                    (attempts, new_lock, uid),
                )
                conn.commit()
                return None, msg
            return None, "Invalid credentials"


def login_user_streamlit(st, username_or_email: str, password: str):
    user, error_msg = authenticate_user(username_or_email, password)

    if not user:
        return False, error_msg

    token, expires_at = create_session_token(user["id"])

    st.session_state["session_token"] = token
    st.session_state["user_id"] = user["id"]
    st.session_state["username"] = user["username"]
    st.session_state["user_role"] = user["role"]
    st.session_state["email"] = user.get("email")
    st.session_state["name"] = user.get("name")
    st.session_state["surname"] = user.get("surname")
    st.session_state["user_name_full"] = f"{user['name']} {user['surname']}".strip()
    st.session_state["user_station_id"] = user["station_id"]
    st.session_state["user_region_id"] = user["region_id"]
    st.session_state["user_telegram_chat_id"] = user["telegram_chat_id"]
    st.session_state["force_password_change"] = user.get("force_change", False)

    st.session_state["dark_mode"] = user.get("dark_mode", False)

    return True, "Login successful"


def logout_user_streamlit(st):
    token = st.session_state.get("session_token")

    if token:
        destroy_session_token(token)

    for key in [
        "session_token",
        "user_id",
        "username",
        "user_role",
        "force_password_change",
    ]:
        if key in st.session_state:
            del st.session_state[key]

    try:
        if "session_token" in st.query_params:
            del st.query_params["session_token"]
    except Exception:
        pass
