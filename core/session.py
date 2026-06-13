# core/session.py
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
from core.database import get_connection


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session_token(
    user_id: int, tenant_id: int, ttl_hours: int = 8
) -> Tuple[str, str]:
    """
    Creates a secure token, stores in sessions table with expiry.
    Returns (token, expires_at_iso)
    """
    with get_connection(platform_access=True) as conn:
        cur = conn.cursor()
        token = secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(hours=ttl_hours)
        cur.execute(
            "INSERT INTO sessions (token, tenant_id, user_id, created_at, expires_at) VALUES (%s,%s,%s,%s,%s)",
            (
                token_hash,
                tenant_id,
                user_id,
                created_at.isoformat(),
                expires_at.isoformat(),
            ),
        )
        conn.commit()
        return token, expires_at.isoformat()


def validate_session_token(token: str) -> Optional[Dict[str, int]]:
    """
    Validate token and return user_id if valid and not expired.
    """
    if not token:
        return None
    token_hash = _hash_token(token)
    with get_connection(platform_access=True) as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT tenant_id, user_id, expires_at FROM sessions WHERE token = %s",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        tenant_id, user_id, expires_at = row
        try:
            if isinstance(expires_at, str):
                expiry_dt = datetime.fromisoformat(expires_at)
            else:
                expiry_dt = expires_at

            if expiry_dt and expiry_dt < datetime.utcnow():
                # expired -> delete
                cur.execute("DELETE FROM sessions WHERE token = %s", (token_hash,))
                conn.commit()
                return None
        except Exception:
            return None
        return {"tenant_id": tenant_id, "user_id": user_id}


def destroy_session_token(token: str):
    token_hash = _hash_token(token)
    with get_connection(platform_access=True) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token = %s", (token_hash,))
        conn.commit()
