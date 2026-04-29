# gentstation_opus/core/activity_logger.py
import streamlit as st
import logging

logger = logging.getLogger("gentstation.activity_logger")


def get_client_ip():
    """Best-effort retrieval of client IP address from headers."""
    headers = {}
    try:
        # Streamlit 1.34+ context-based headers (preferred)
        if hasattr(st, "context"):
            headers = st.context.headers
        else:
            # Fallback for very old versions, using a dynamic lookup to avoid static analysis warnings
            import importlib

            try:
                mod_name = "streamlit.web.server.websocket_headers"
                mod = importlib.import_module(mod_name)
                if hasattr(mod, "_get_websocket_headers"):
                    headers = mod._get_websocket_headers()
            except ImportError:
                pass

        if headers:
            # Check various common IP headers (case-insensitive)
            # st.context.headers is a dict-like object
            for key in ["X-Forwarded-For", "X-Real-Ip", "x-forwarded-for", "x-real-ip"]:
                if key in headers:
                    val = headers[key]
                    if val:
                        return val.split(",")[0].strip()
    except Exception:
        pass
    return None


def log_activity(conn, action, details):
    user = st.session_state.get("username", "System")  # Use username from session state
    ip = get_client_ip()

    try:
        # Attempt insert with ip_address column
        conn.execute(
            "INSERT INTO activity_logs (user_name, action, details, ip_address) VALUES (%s, %s, %s, %s)",
            (user, action, details, ip),
        )
        conn.commit()
    except Exception:
        # Fallback for legacy DB schema: append IP to details
        try:
            final_details = f"{details} [IP: {ip}]" if ip else details
            conn.execute(
                "INSERT INTO activity_logs (user_name, action, details) VALUES (%s, %s, %s)",
                (user, action, final_details),
            )
            conn.commit()
        except Exception as e:
            logger.debug("log_activity error: %s", e)
