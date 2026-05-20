from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, settings

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

NEW_TABLES = [
    "ticket_timeline_events",
    "password_reset_requests",
    "provisioning_requests",
    "ad_group_permissions",
]


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def migrate_schema():
    """Lightweight migrations for existing SQLite databases."""
    column_migrations = [
        ("ad_groups", "group_type", "VARCHAR(32) DEFAULT 'security'"),
        ("ad_groups", "mapped_role", "VARCHAR(32)"),
        ("ad_groups", "role_priority", "INTEGER DEFAULT 0"),
        ("users", "job_title", "VARCHAR(128)"),
        ("users", "role_sync_from_groups", "BOOLEAN DEFAULT 1"),
        ("tickets", "ticket_type", "VARCHAR(32) DEFAULT 'incident'"),
        ("tickets", "impact", "VARCHAR(16) DEFAULT 'medium'"),
        ("tickets", "urgency", "VARCHAR(16) DEFAULT 'medium'"),
        ("tickets", "tags", "VARCHAR(512)"),
        ("devices", "manufacturer", "VARCHAR(64)"),
        ("devices", "model", "VARCHAR(128)"),
        ("devices", "serial_number", "VARCHAR(128)"),
        ("devices", "status", "VARCHAR(32) DEFAULT 'in_stock'"),
        ("devices", "purchase_date", "DATETIME"),
        ("devices", "warranty_expires", "DATETIME"),
        ("devices", "notes", "TEXT"),
        ("devices", "updated_at", "DATETIME"),
        ("audit_logs", "summary", "VARCHAR(512)"),
        ("audit_logs", "severity", "VARCHAR(16) DEFAULT 'info'"),
        ("audit_logs", "request_path", "VARCHAR(255)"),
    ]
    with engine.begin() as conn:
        for table, column, col_type in column_migrations:
            if _column_exists(table, "id") and not _column_exists(table, column):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))

        from app import models  # noqa: F401

        existing = set(inspect(engine).get_table_names())
        for name in NEW_TABLES:
            if name not in existing and name in Base.metadata.tables:
                Base.metadata.tables[name].create(bind=conn, checkfirst=True)


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema()
