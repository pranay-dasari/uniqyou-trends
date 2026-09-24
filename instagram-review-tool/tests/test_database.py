import sqlite3

from sqlalchemy import inspect

from database.db import get_session, init_db
from database.models import Comment, Post, Upvote


def test_init_db_creates_file_and_tables(tmp_path):
    db_path = tmp_path / "nested" / "dir" / "app.db"
    engine = init_db(f"sqlite:///{db_path}")

    assert db_path.exists()
    assert {"posts", "comments", "upvotes"} <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_init_db_is_idempotent_and_keeps_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(url)
    with get_session() as session:
        session.add(Post(instagram_url="https://www.instagram.com/p/ABCDE/"))

    init_db(url)  # simulates an app restart
    with get_session() as session:
        assert session.query(Post).count() == 1


def test_posts_schema_matches_spec(db):
    with sqlite3.connect(db) as conn:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(posts)")}
    assert {"id", "instagram_url", "media_url", "caption", "created_at"} <= set(columns)
    assert columns["instagram_url"][3] == 1  # NOT NULL


def test_deleting_post_cascades(db):
    with get_session() as session:
        post = Post(instagram_url="https://www.instagram.com/p/ABCDE/")
        session.add(post)
        session.flush()
        session.add_all([Comment(post_id=post.id, comment_text="hi"), Upvote(post_id=post.id)])

    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM posts")
        assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM upvotes").fetchone()[0] == 0


def test_created_at_defaults(db):
    with get_session() as session:
        post = Post(instagram_url="https://www.instagram.com/p/ABCDE/")
        session.add(post)
        session.flush()
        session.refresh(post)
        assert post.created_at is not None


def test_postgres_urls_use_psycopg_and_require_tls():
    from database.db import normalize_database_url

    for raw in ("postgresql://u:p@host:5432/db", "postgres://u:p@host:5432/db"):
        url = normalize_database_url(raw)
        assert url.drivername == "postgresql+psycopg"
        assert url.query["sslmode"] == "require"

    kept = normalize_database_url("postgresql://u:p@host/db?sslmode=verify-full")
    assert kept.query["sslmode"] == "verify-full"
    assert normalize_database_url("sqlite:///x.db").drivername == "sqlite"


def test_settings_repr_hides_database_password(monkeypatch):
    from config import get_settings

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:s3cret-pw@host:5432/db")
    assert "s3cret-pw" not in repr(get_settings())
