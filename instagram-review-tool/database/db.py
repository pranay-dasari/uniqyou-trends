"""Engine/session management and schema creation.

SQLite (default, a local file) or Postgres (e.g. Supabase) — chosen by DATABASE_URL.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    # SQLite ignores FOREIGN KEY / ON DELETE CASCADE unless this is set per connection.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def normalize_database_url(database_url: str) -> URL:
    """Parse DATABASE_URL, accepting Postgres URLs exactly as Supabase shows them.

    `postgres://` and `postgresql://` are pointed at the psycopg 3 driver, and
    TLS is required unless the URL already says otherwise.
    """
    url = make_url(database_url)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
        if "sslmode" not in url.query:
            url = url.update_query_dict({"sslmode": "require"})
    return url


def _enable_row_level_security(engine: Engine) -> None:
    """Supabase exposes tables in `public` through its REST API. Turning RLS on
    with no policies closes that path; the app connects as the table owner, so
    its own queries are unaffected."""
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))


def init_db(database_url: str | None = None) -> Engine:
    """Create the database file and tables if they don't exist yet.

    Safe to call on every start. Passing a URL (re)binds the module to that
    database, which is how tests point at a temporary file.
    """
    global _engine, _SessionLocal

    if database_url is None:
        from config import get_settings

        database_url = get_settings().database_url

    url = normalize_database_url(database_url)
    is_sqlite = url.get_backend_name() == "sqlite"
    if is_sqlite and url.database not in (None, "", ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    if _engine is not None:
        _engine.dispose()

    if is_sqlite:
        engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    else:
        # pool_pre_ping: hosted poolers (Supabase) drop idle connections.
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
    Base.metadata.create_all(engine)
    if url.get_backend_name() == "postgresql":
        _enable_row_level_security(engine)

    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Transactional session: commits on success, rolls back on error."""
    if _SessionLocal is None:
        init_db()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
