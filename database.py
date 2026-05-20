from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATA_DIR, settings

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
    migrations = [
        ("ad_groups", "group_type", "VARCHAR(32) DEFAULT 'security'"),
        ("ad_groups", "mapped_role", "VARCHAR(32)"),
        ("ad_groups", "role_priority", "INTEGER DEFAULT 0"),
        ("users", "job_title", "VARCHAR(128)"),
        ("users", "role_sync_from_groups", "BOOLEAN DEFAULT 1"),
    ]
    with engine.begin() as conn:
        for table, column, col_type in migrations:
            if not _column_exists(table, column):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))

        if "ad_group_permissions" not in inspect(engine).get_table_names():
            from app import models  # noqa: F401

            Base.metadata.tables["ad_group_permissions"].create(bind=conn, checkfirst=True)


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_schema()
