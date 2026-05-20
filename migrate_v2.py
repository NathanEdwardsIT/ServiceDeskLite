"""Apply v2 schema updates (timeline, provisioning, inventory) to existing databases."""

from app.database import init_db

if __name__ == "__main__":
    init_db()
    print("Schema v2 migration complete.")
