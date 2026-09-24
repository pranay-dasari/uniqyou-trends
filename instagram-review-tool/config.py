"""Application settings.

Values are read from environment variables (optionally loaded from a local
.env file) and fall back to Streamlit secrets. Nothing secret lives in code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

DEFAULT_DATABASE_URL = f"sqlite:///{BASE_DIR / 'data' / 'instagram_review.db'}"


def _read_setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value.strip()
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        # No secrets.toml, or not running under Streamlit.
        pass
    return default


@dataclass(frozen=True)
class Settings:
    instagram_access_token: str | None
    graph_api_version: str
    instagram_timeout_seconds: float
    database_url: str

    def __repr__(self) -> str:  # never print the token or the database password
        from sqlalchemy.engine import make_url

        try:
            safe_db_url = make_url(self.database_url).render_as_string(hide_password=True)
        except Exception:
            safe_db_url = "<unparseable>"
        return (
            f"Settings(graph_api_version={self.graph_api_version!r}, "
            f"database_url={safe_db_url!r}, instagram_access_token=***)"
        )


def get_settings() -> Settings:
    return Settings(
        instagram_access_token=_read_setting("INSTAGRAM_ACCESS_TOKEN"),
        graph_api_version=_read_setting("META_GRAPH_API_VERSION", "v25.0"),
        instagram_timeout_seconds=float(_read_setting("INSTAGRAM_TIMEOUT_SECONDS", "10")),
        database_url=_read_setting("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
