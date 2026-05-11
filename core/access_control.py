"""
Access Control Module - GentStationAI

Centralizes page configurations and role-based access logic.
"""

import os

# List of usernames that bypass all role-based restrictions
SUPERUSERS = os.getenv("GSAI_SUPERUSERS", "admin").split(",")


PAGE_CONFIG = {
    "Dashboard": {
        "id": "Dashboard",
        "icon": "🏠",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
    "Personal Dashboard": {
        "id": "Personal Dashboard",
        "icon": "🧭",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
    "Shifts": {
        "id": "Shifts",
        "icon": "🕒",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
    "Regions": {
        "id": "Regions",
        "icon": "🌍",
        "roles": ["General Manager"],
    },
    "Stations": {
        "id": "Stations",
        "icon": "⛽",
        "roles": ["General Manager", "Region Manager"],
    },
    "Map View": {
        "id": "Map View",
        "icon": "🗺️",
        "roles": ["General Manager", "Region Manager"],
    },
    "Employees": {
        "id": "Employees",
        "icon": "👥",
        "roles": ["General Manager"],
    },
    "AI Reports": {
        "id": "AI Reports",
        "icon": "📈",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
        ],
    },
    "AI Alerts": {
        "id": "AI Alerts",
        "icon": "🚨",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
        ],
    },
    "AI Monitoring": {
        "id": "AI Monitoring",
        "icon": "🖥️",
        "roles": ["General Manager"],
    },
    "Audit Log": {
        "id": "Audit Log",
        "icon": "🛡️",
        "roles": ["General Manager"],
    },
    "Admin Users": {
        "id": "Admin Users",
        "icon": "👤",
        "roles": ["General Manager"],
    },
    "Data Import": {
        "id": "Data Import",
        "icon": "📤",
        "roles": ["General Manager"],
    },
    "Settings": {
        "id": "Settings",
        "icon": "⚙️",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
    "Help": {
        "id": "Help",
        "icon": "❓",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
}


def has_access(page_id: str, user_role: str, username: str = None) -> bool:
    """Returns True if the given role has permission to access the page."""
    if not user_role:
        return False

    # Superuser bypass
    if username in SUPERUSERS:
        return True

    config = PAGE_CONFIG.get(page_id)
    if not config:
        return False
    return user_role in config.get("roles", [])
