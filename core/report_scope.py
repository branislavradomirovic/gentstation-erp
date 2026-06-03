from typing import Dict, List, Optional


ACTIVE_REPORTING_ROLES = {
    "Employee",
    "Gas Station Manager",
    "Region Manager",
    "General Manager",
}


def get_user_scope(conn, user_id: int) -> Optional[Dict]:
    row = conn.execute(
        """
        SELECT id, role, station_id, region_id, manager_user_id, email, telegram_chat_id,
               COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    ).fetchone()
    if not row:
        return None

    return {
        "user_id": row[0],
        "role": row[1],
        "station_id": row[2],
        "region_id": row[3],
        "manager_user_id": row[4],
        "email": row[5],
        "telegram_chat_id": row[6],
        "full_name": row[7],
    }


def get_scope_filter_clause(role: str, user_id: int, conn):
    if role == "Region Manager":
        region_row = conn.execute(
            "SELECT region_id FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
        if region_row and region_row[0]:
            return "AND st.region_id = %s", [region_row[0]]
        return "AND 1=0", []

    if role == "Gas Station Manager":
        station_row = conn.execute(
            "SELECT station_id FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
        if station_row and station_row[0]:
            return "AND s.station_id = %s", [station_row[0]]
        return "AND 1=0", []

    if role == "General Manager":
        return "", []

    return "AND 1=0", []


def get_station_manager_options(conn) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT id,
               COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name,
               station_id
        FROM users
        WHERE role = 'Gas Station Manager'
        ORDER BY full_name
        """
    ).fetchall()
    return [{"id": row[0], "label": row[1], "station_id": row[2]} for row in rows]


def get_region_manager_options(conn) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT id,
               COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name,
               region_id
        FROM users
        WHERE role = 'Region Manager'
        ORDER BY full_name
        """
    ).fetchall()
    return [{"id": row[0], "label": row[1], "region_id": row[2]} for row in rows]


def get_general_manager_options(conn) -> List[Dict]:
    rows = conn.execute(
        """
        SELECT id,
               COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username) AS full_name
        FROM users
        WHERE role = 'General Manager'
        ORDER BY full_name
        """
    ).fetchall()
    return [{"id": row[0], "label": row[1]} for row in rows]

