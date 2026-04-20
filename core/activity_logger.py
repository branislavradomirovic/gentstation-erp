# gentstation_opus/core/activity_logger.py
import streamlit as st
import logging
try:
    from streamlit.web.server.websocket_headers import _get_websocket_headers
except ImportError:
    def _get_websocket_headers(): return {}

def get_client_ip():
    """Best-effort retrieval of client IP address from WebSocket headers."""
    try:
        headers = _get_websocket_headers()
        if headers:
            if "X-Forwarded-For" in headers:
                return headers["X-Forwarded-For"].split(",")[0].strip()
            if "X-Real-Ip" in headers:
                return headers["X-Real-Ip"]
    except Exception:
        pass
    return None

def log_activity(conn, action, details):
    user = st.session_state.get("user_name", "System")
    ip = get_client_ip()

    try:
        # Attempt insert with ip_address column
        conn.execute(
            "INSERT INTO activity_logs (user_name, action, details, ip_address) VALUES (%s, %s, %s, %s)",
            (user, action, details, ip)
        )
        conn.commit()
    except Exception:
        # Fallback for legacy DB schema: append IP to details
        try:
            final_details = f"{details} [IP: {ip}]" if ip else details
            conn.execute(
                "INSERT INTO activity_logs (user_name, action, details) VALUES (%s, %s, %s)",
                (user, action, final_details)
            )
            conn.commit()
        except Exception as e:
            logger.debug("log_activity error: %s", e)
logger = logging.getLogger("gentstation.activity_logger")
