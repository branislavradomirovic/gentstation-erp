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

def authenticate_user(username_or_email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Verify credentials with lockout logic. 
    Returns (user_dict, error_message).
    """
    conn = get_connection()
    cur = conn.cursor()
    # Try username, then email
    cur.execute("""
        SELECT id, username, email, password_hash, role, is_active, failed_attempts, locked_until, dark_mode_enabled
        FROM users WHERE username = ? OR email = ?
    """, (username_or_email, username_or_email))
    
    row = cur.fetchone()
    if not row:
        return None, "Invalid credentials"

    uid, uname, uemail, phash, role, active, attempts, locked_until, dark_mode = row

    # Check Maintenance Mode
    try:
        m_row = cur.execute("SELECT value FROM system_settings WHERE key='maintenance_mode'").fetchone()
        if m_row and m_row[0] == '1':
            if role != "General Manager":
                return None, "⚠️ System is in Maintenance Mode. Admin login only."
    except Exception:
        pass # Fail open if settings table issue (schema not updated yet)

    # 1. Check if locked
    if locked_until:
        lock_time = datetime.fromisoformat(locked_until)
        if lock_time > datetime.utcnow():
            remaining_mins = int((lock_time - datetime.utcnow()).total_seconds() / 60) + 1
            return None, f"Account locked. Try again in {remaining_mins} minutes."

    if not active:
        return None, "Account deactivated."

    # 2. Verify Password
    if verify_password(password, phash):
        # Success: Reset counters
        cur.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (uid,))
        conn.commit()
        
        user = {"id": uid, "username": uname, "email": uemail, "role": role, "is_active": bool(active), "dark_mode": bool(dark_mode)}
        return user, None
    else:
        # Failure: Increment counters
        attempts = (attempts or 0) + 1
        new_lock = None
        msg = "Invalid credentials"
        
        if attempts >= MAX_LOGIN_ATTEMPTS:
            new_lock = (datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)).isoformat()
            msg = f"Account locked due to too many failed attempts ({LOCKOUT_DURATION_MINUTES} min)."
            
        cur.execute("UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?", (attempts, new_lock, uid))
        conn.commit()
        return None, msg

def login_user_streamlit(st, username_or_email: str, password: str):
    user, error_msg = authenticate_user(username_or_email, password)

    if not user:
        return False, error_msg

    token, expires_at = create_session_token(user["id"])

    st.session_state["session_token"] = token
    st.session_state["user_id"] = user["id"]
    st.session_state["username"] = user["username"]
    st.session_state["user_role"] = user["role"]
    st.session_state["dark_mode"] = user.get("dark_mode", False)

    return True, "Login successful"

def logout_user_streamlit(st):
    token = st.session_state.get("session_token")

    if token:
        destroy_session_token(token)

    for key in ["session_token", "user_id", "username", "user_role"]:
        if key in st.session_state:
            del st.session_state[key]