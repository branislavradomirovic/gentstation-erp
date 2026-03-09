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

def create_user(username: str, password: str, email: Optional[str], role: str = "Employee") -> Dict[str, Any]:
    """Create new user in users table. Returns user row dict."""
    conn = get_connection()
    cur = conn.cursor()
    pw_hash = hash_password(password)
    cur.execute("""
        INSERT INTO users (username, email, password_hash, role, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
    """, (username, email, pw_hash, role, datetime.utcnow().isoformat()))
    conn.commit()
    uid = cur.lastrowid
    return {"id": uid, "username": username, "email": email, "role": role}

def authenticate_user(username_or_email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Verify credentials. Returns user dict on success; otherwise None.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Try username, then email
    cur.execute("SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = ? OR email = ?", (username_or_email, username_or_email))
    row = cur.fetchone()
    if not row:
        return None
    user = {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "password_hash": row[3],
        "role": row[4],
        "is_active": bool(row[5])
    }
    if not user["is_active"]:
        return None
    if verify_password(password, user["password_hash"]):
        # Remove password_hash before returning
        user.pop("password_hash", None)
        return user
    return None

def login_user_streamlit(st, username_or_email: str, password: str):
    user = authenticate_user(username_or_email, password)

    if not user:
        return False, "Invalid credentials"

    token, expires_at = create_session_token(user["id"])

    st.session_state["session_token"] = token
    st.session_state["user_id"] = user["id"]
    st.session_state["username"] = user["username"]
    st.session_state["user_role"] = user["role"]

    return True, "Login successful"

def logout_user_streamlit(st):
    token = st.session_state.get("session_token")

    if token:
        destroy_session_token(token)

    for key in ["session_token", "user_id", "username", "user_role"]:
        if key in st.session_state:
            del st.session_state[key]