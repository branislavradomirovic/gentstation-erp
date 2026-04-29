import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.database import get_connection


def run_migration():
    conn = get_connection()
    cur = conn.cursor()

    print("🚀 Starting User/Employee Merged Migration...")

    try:
        # 1. Update existing Users with Employee metadata where email matches
        print("Updating existing user profiles...")
        cur.execute(
            """
            UPDATE users u
            SET name = e.name,
                surname = e.surname,
                station_id = e.station_id,
                region_id = e.region_id,
                telegram_chat_id = e.telegram_chat_id
            FROM employees e
            WHERE LOWER(u.email) = LOWER(e.email)
        """
        )

        # 2. Re-map IDs for director_regions
        print("Re-mapping Director/Region relationships...")
        cur.execute(
            """
            INSERT INTO director_regions (user_id, region_id)
            SELECT u.id, dr.region_id
            FROM director_regions_old dr
            JOIN employees e ON dr.employee_id = e.id
            JOIN users u ON LOWER(e.email) = LOWER(u.email)
            ON CONFLICT DO NOTHING
        """
        )

        # 3. Update foreign keys in operational tables mapping old employee_id to user_id
        print("Updating Submissions links...")
        cur.execute(
            """
            UPDATE submissions s
            SET employee_id = u.id
            FROM employees e
            JOIN users u ON LOWER(e.email) = LOWER(u.email)
            WHERE s.employee_id = e.id
        """
        )

        print("Updating Shift links...")
        cur.execute(
            """
            UPDATE employee_shifts es
            SET employee_id = u.id
            FROM employees e
            JOIN users u ON LOWER(e.email) = LOWER(u.email)
            WHERE es.employee_id = e.id
        """
        )

        conn.commit()
        print(
            "✅ Migration complete. 'employees' table can now be safely archived/dropped."
        )

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")


if __name__ == "__main__":
    run_migration()
