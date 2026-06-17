from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


USER_LIFECYCLE_STATES = {
    "invited",
    "active",
    "suspended",
    "offboarded",
    "password_reset_required",
}

MANAGED_USER_ROLES = {
    "Employee",
    "Gas Station Supervisor",
    "Gas Station Manager",
    "Region Manager",
    "General Manager",
}

IMPORT_TEMPLATE_COLUMNS = [
    "first_name",
    "surname",
    "email",
    "role",
    "station_name",
    "region_name",
    "manager_email",
    "phone",
    "telegram_chat_id",
]


@dataclass
class ImportPreviewResult:
    preview_rows: List[Dict]
    valid_rows: List[Dict]
    error_count: int


def _normalized_text(value: Optional[str]) -> Optional[str]:
    clean = (value or "").strip()
    return clean or None


def build_user_import_template_rows() -> List[Dict]:
    return [
        {
            "first_name": "Ana",
            "surname": "Markovic",
            "email": "ana.markovic@example.com",
            "role": "Employee",
            "station_name": "Station 101",
            "region_name": "",
            "manager_email": "manager.station101@example.com",
            "phone": "+381600000001",
            "telegram_chat_id": "",
        },
        {
            "first_name": "Milan",
            "surname": "Petrovic",
            "email": "milan.petrovic@example.com",
            "role": "Region Manager",
            "station_name": "",
            "region_name": "Belgrade Region",
            "manager_email": "gm@example.com",
            "phone": "+381600000002",
            "telegram_chat_id": "",
        },
    ]


def _load_station(conn, tenant_id: int, station_id: Optional[int]) -> Optional[Tuple[int, Optional[int], str]]:
    if not station_id:
        return None
    return conn.execute(
        """
        SELECT id, region_id, name
        FROM stations
        WHERE tenant_id = %s AND id = %s
        """,
        (tenant_id, int(station_id)),
    ).fetchone()


def _load_region(conn, tenant_id: int, region_id: Optional[int]) -> Optional[Tuple[int, str]]:
    if not region_id:
        return None
    return conn.execute(
        """
        SELECT id, name
        FROM regions
        WHERE tenant_id = %s AND id = %s
        """,
        (tenant_id, int(region_id)),
    ).fetchone()


def _load_manager(
    conn,
    tenant_id: int,
    manager_user_id: Optional[int],
) -> Optional[Tuple[int, str, Optional[int], Optional[int], str]]:
    if not manager_user_id:
        return None
    return conn.execute(
        """
        SELECT
            id,
            role,
            station_id,
            region_id,
            COALESCE(email, username)
        FROM users
        WHERE tenant_id = %s AND id = %s
        """,
        (tenant_id, int(manager_user_id)),
    ).fetchone()


def validate_user_assignment(
    conn,
    *,
    tenant_id: int,
    role: str,
    station_id: Optional[int] = None,
    region_id: Optional[int] = None,
    manager_user_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Dict:
    if role not in MANAGED_USER_ROLES:
        raise ValueError(f"Unsupported role: {role}")
    if user_id is not None and manager_user_id is not None and int(user_id) == int(manager_user_id):
        raise ValueError("A user cannot be assigned as their own manager.")

    station_row = _load_station(conn, tenant_id, station_id)
    region_row = _load_region(conn, tenant_id, region_id)
    manager_row = _load_manager(conn, tenant_id, manager_user_id)

    if station_id and not station_row:
        raise ValueError("Assigned station must belong to the current tenant.")
    if region_id and not region_row:
        raise ValueError("Assigned region must belong to the current tenant.")
    if manager_user_id and not manager_row:
        raise ValueError("Assigned manager must belong to the current tenant.")

    normalized_station_id = int(station_row[0]) if station_row else None
    normalized_region_id = int(region_row[0]) if region_row else None
    normalized_manager_user_id = int(manager_row[0]) if manager_row else None

    if role == "General Manager":
        return {
            "station_id": None,
            "region_id": None,
            "manager_user_id": None,
        }

    if role == "Region Manager":
        if not region_row:
            raise ValueError("Region Manager requires region assignment.")
        if not manager_row or manager_row[1] != "General Manager":
            raise ValueError("Region Manager requires a General Manager as manager.")
        return {
            "station_id": None,
            "region_id": normalized_region_id,
            "manager_user_id": normalized_manager_user_id,
        }

    if role in {"Gas Station Manager", "Gas Station Supervisor", "Employee"}:
        if not station_row:
            raise ValueError(f"{role} requires station assignment.")
        station_region_id = station_row[1]
        if station_region_id is None:
            raise ValueError("Assigned station must belong to a region.")
        normalized_region_id = int(station_region_id)

        if role in {"Gas Station Manager", "Gas Station Supervisor"}:
            if not manager_row or manager_row[1] != "Region Manager":
                raise ValueError(f"{role} requires a Region Manager as manager.")
            if manager_row[3] != normalized_region_id:
                raise ValueError("Assigned Region Manager must belong to the station region.")
        elif role == "Employee":
            if not manager_row or manager_row[1] != "Gas Station Manager":
                raise ValueError("Employee requires a Gas Station Manager as manager.")
            if manager_row[2] != normalized_station_id:
                raise ValueError("Assigned Gas Station Manager must belong to the employee station.")

        return {
            "station_id": normalized_station_id,
            "region_id": normalized_region_id,
            "manager_user_id": normalized_manager_user_id,
        }

    raise ValueError(f"Unsupported role: {role}")


def update_user_profile(
    conn,
    *,
    tenant_id: int,
    user_id: int,
    email: str,
    role: str,
    first_name: Optional[str],
    surname: Optional[str],
    station_id: Optional[int],
    region_id: Optional[int],
    manager_user_id: Optional[int],
    phone: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
) -> Dict:
    normalized = validate_user_assignment(
        conn,
        tenant_id=tenant_id,
        role=role,
        station_id=station_id,
        region_id=region_id,
        manager_user_id=manager_user_id,
        user_id=user_id,
    )
    clean_email = _normalized_text(email)
    if not clean_email:
        raise ValueError("Email is required.")

    conn.execute(
        """
        UPDATE users
        SET email = %s,
            username = %s,
            role = %s,
            name = %s,
            surname = %s,
            station_id = %s,
            region_id = %s,
            manager_user_id = %s,
            phone = %s,
            telegram_chat_id = %s,
            updated_at = NOW()
        WHERE tenant_id = %s AND id = %s
        """,
        (
            clean_email,
            clean_email,
            role,
            _normalized_text(first_name),
            _normalized_text(surname),
            normalized["station_id"],
            normalized["region_id"],
            normalized["manager_user_id"],
            _normalized_text(phone),
            _normalized_text(telegram_chat_id),
            tenant_id,
            user_id,
        ),
    )
    conn.commit()
    return normalized


def set_user_lifecycle_state(
    conn,
    *,
    tenant_id: int,
    user_id: int,
    lifecycle_state: str,
) -> None:
    if lifecycle_state not in USER_LIFECYCLE_STATES:
        raise ValueError(f"Unsupported lifecycle state: {lifecycle_state}")

    is_active = lifecycle_state not in {"suspended", "offboarded"}
    force_password_change = lifecycle_state in {"invited", "password_reset_required"}

    conn.execute(
        """
        UPDATE users
        SET lifecycle_state = %s,
            is_active = %s,
            force_password_change = %s,
            updated_at = NOW()
        WHERE tenant_id = %s AND id = %s
        """,
        (
            lifecycle_state,
            is_active,
            force_password_change,
            tenant_id,
            user_id,
        ),
    )
    conn.commit()


def mark_user_password_changed(conn, *, tenant_id: int, user_id: int) -> None:
    conn.execute(
        """
        UPDATE users
        SET lifecycle_state = 'active',
            force_password_change = FALSE,
            is_active = TRUE,
            updated_at = NOW()
        WHERE tenant_id = %s AND id = %s
        """,
        (tenant_id, user_id),
    )
    conn.commit()


def get_user_status_rows(conn, tenant_id: int) -> List[Dict]:
    rows = conn.execute(
        """
        WITH submission_stats AS (
            SELECT
                employee_id,
                MIN(timestamp) AS first_submission_at,
                MAX(timestamp) AS last_submission_at
            FROM submissions
            WHERE tenant_id = %s
            GROUP BY employee_id
        )
        SELECT
            u.id,
            COALESCE(NULLIF(TRIM(COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'')), ''), u.email, u.username) AS full_name,
            u.email,
            u.role,
            u.lifecycle_state,
            u.is_active,
            u.telegram_chat_id,
            u.station_id,
            s.name AS station_name,
            COALESCE(u.region_id, s.region_id) AS effective_region_id,
            COALESCE(r.name, rs.name) AS region_name,
            mgr.email AS manager_email,
            stats.first_submission_at,
            stats.last_submission_at
        FROM users u
        LEFT JOIN stations s ON s.tenant_id = u.tenant_id AND s.id = u.station_id
        LEFT JOIN regions r ON r.tenant_id = u.tenant_id AND r.id = u.region_id
        LEFT JOIN regions rs ON rs.tenant_id = u.tenant_id AND rs.id = s.region_id
        LEFT JOIN users mgr ON mgr.tenant_id = u.tenant_id AND mgr.id = u.manager_user_id
        LEFT JOIN submission_stats stats ON stats.employee_id = u.id
        WHERE u.tenant_id = %s
        ORDER BY u.id DESC
        """,
        (tenant_id, tenant_id),
    ).fetchall()

    status_rows: List[Dict] = []
    for row in rows:
        missing_manager = row[3] != "General Manager" and not row[11]
        missing_station = row[3] in {"Employee", "Gas Station Supervisor", "Gas Station Manager"} and not row[7]
        missing_region = row[3] in {"Employee", "Gas Station Supervisor", "Gas Station Manager", "Region Manager"} and not row[9]
        status_rows.append(
            {
                "user_id": row[0],
                "full_name": row[1],
                "email": row[2],
                "role": row[3],
                "lifecycle_state": row[4],
                "is_active": bool(row[5]),
                "telegram_linked": bool(row[6]),
                "station_name": row[8],
                "region_name": row[10],
                "manager_email": row[11],
                "first_video_received": bool(row[12]),
                "last_submission_date": row[13],
                "missing_manager": missing_manager,
                "missing_station": missing_station,
                "missing_region": missing_region,
            }
        )
    return status_rows


def preview_user_import(conn, *, tenant_id: int, content_bytes: bytes) -> ImportPreviewResult:
    decoded = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))
    if reader.fieldnames is None:
        raise ValueError("CSV file is empty.")

    missing_columns = [column for column in IMPORT_TEMPLATE_COLUMNS if column not in reader.fieldnames]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    preview_rows: List[Dict] = []
    valid_rows: List[Dict] = []
    seen_emails = set()

    for index, row in enumerate(reader, start=2):
        first_name = _normalized_text(row.get("first_name"))
        surname = _normalized_text(row.get("surname"))
        email = _normalized_text(row.get("email"))
        role = _normalized_text(row.get("role"))
        station_name = _normalized_text(row.get("station_name"))
        region_name = _normalized_text(row.get("region_name"))
        manager_email = _normalized_text(row.get("manager_email"))
        phone = _normalized_text(row.get("phone"))
        telegram_chat_id = _normalized_text(row.get("telegram_chat_id"))

        station_id = None
        region_id = None
        manager_user_id = None
        error_message = None

        try:
            if not first_name:
                raise ValueError("First name is required.")
            if not email:
                raise ValueError("Email is required.")
            if role not in MANAGED_USER_ROLES:
                raise ValueError("Role is invalid.")
            lowered_email = email.lower()
            if lowered_email in seen_emails:
                raise ValueError("Email is duplicated in the import file.")
            existing_user = conn.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND LOWER(email) = LOWER(%s)",
                (tenant_id, email),
            ).fetchone()
            if existing_user:
                raise ValueError("Email already exists for this tenant.")

            if station_name:
                station_row = conn.execute(
                    "SELECT id FROM stations WHERE tenant_id = %s AND LOWER(name) = LOWER(%s)",
                    (tenant_id, station_name),
                ).fetchone()
                if not station_row:
                    raise ValueError("Station name was not found for this tenant.")
                station_id = int(station_row[0])

            if region_name:
                region_row = conn.execute(
                    "SELECT id FROM regions WHERE tenant_id = %s AND LOWER(name) = LOWER(%s)",
                    (tenant_id, region_name),
                ).fetchone()
                if not region_row:
                    raise ValueError("Region name was not found for this tenant.")
                region_id = int(region_row[0])

            if manager_email:
                manager_row = conn.execute(
                    "SELECT id FROM users WHERE tenant_id = %s AND LOWER(email) = LOWER(%s)",
                    (tenant_id, manager_email),
                ).fetchone()
                if not manager_row:
                    raise ValueError("Manager email was not found for this tenant.")
                manager_user_id = int(manager_row[0])

            normalized = validate_user_assignment(
                conn,
                tenant_id=tenant_id,
                role=role,
                station_id=station_id,
                region_id=region_id,
                manager_user_id=manager_user_id,
            )
            preview_rows.append(
                {
                    "row_number": index,
                    "status": "valid",
                    "email": email,
                    "role": role,
                    "station_name": station_name,
                    "region_name": region_name,
                    "manager_email": manager_email,
                    "message": "Ready to import.",
                }
            )
            valid_rows.append(
                {
                    "first_name": first_name,
                    "surname": surname,
                    "email": email,
                    "role": role,
                    "station_id": normalized["station_id"],
                    "region_id": normalized["region_id"],
                    "manager_user_id": normalized["manager_user_id"],
                    "phone": phone,
                    "telegram_chat_id": telegram_chat_id,
                }
            )
            seen_emails.add(lowered_email)
        except Exception as exc:
            error_message = str(exc)
            preview_rows.append(
                {
                    "row_number": index,
                    "status": "error",
                    "email": email,
                    "role": role,
                    "station_name": station_name,
                    "region_name": region_name,
                    "manager_email": manager_email,
                    "message": error_message,
                }
            )

    return ImportPreviewResult(
        preview_rows=preview_rows,
        valid_rows=valid_rows,
        error_count=sum(1 for row in preview_rows if row["status"] == "error"),
    )


def import_previewed_users(
    conn,
    *,
    tenant_id: int,
    rows: List[Dict],
    default_password: str,
) -> int:
    from core.auth import create_user

    created_count = 0
    for row in rows:
        user = create_user(
            username=row["email"],
            password=default_password,
            email=row["email"],
            role=row["role"],
            name=row["first_name"],
            surname=row["surname"],
            station_id=row["station_id"],
            region_id=row["region_id"],
            manager_user_id=row["manager_user_id"],
            tenant_id=tenant_id,
            phone=row.get("phone"),
            telegram_chat_id=row.get("telegram_chat_id"),
            lifecycle_state="invited",
        )
        if row.get("telegram_chat_id"):
            conn.execute(
                "UPDATE users SET telegram_chat_id = %s WHERE tenant_id = %s AND id = %s",
                (row["telegram_chat_id"], tenant_id, user["id"]),
            )
            conn.commit()
        created_count += 1
    return created_count
