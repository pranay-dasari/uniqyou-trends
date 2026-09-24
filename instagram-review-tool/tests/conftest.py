import pytest

from database.db import init_db
from instagram.client import InstagramClient, InstagramPost


@pytest.fixture
def db(tmp_path):
    """A fresh SQLite database file per test."""
    db_path = tmp_path / "test.db"
    engine = init_db(f"sqlite:///{db_path}")
    yield db_path
    engine.dispose()


class FakeInstagramClient(InstagramClient):
    """Stands in for the real integration: no network calls in tests."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[str] = []

    def get_post(self, instagram_url: str) -> InstagramPost:
        self.calls.append(instagram_url)
        if self.error:
            raise self.error
        return InstagramPost(
            instagram_url=instagram_url,
            media_url=None,
            caption=None,
            embed_html='<blockquote class="instagram-media"></blockquote>',
        )


@pytest.fixture
def fake_client():
    return FakeInstagramClient()
