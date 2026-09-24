"""Post creation and lookup, including Instagram URL validation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.db import get_session
from database.models import Post
from instagram.client import InstagramClient, InstagramPost, get_instagram_client
from services.errors import InvalidInstagramURLError, wrap_db_errors

logger = logging.getLogger(__name__)

INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}

# /p/<code>, /reel/<code>, /reels/<code>, /tv/<code>, optionally prefixed by
# /<username>/ (Instagram's newer share-link format).
_POST_PATH = re.compile(
    r"^/(?:[A-Za-z0-9._]{1,30}/)?(?P<kind>p|reel|reels|tv)/(?P<code>[A-Za-z0-9_-]{5,64})/?$"
)


def normalize_instagram_url(url: str) -> str | None:
    """Return the canonical post URL, or None if `url` isn't an Instagram post URL.

    Canonical form: https://www.instagram.com/<p|reel|tv>/<code>/ with query
    string (e.g. ?igsh= share tracking) and fragment removed, so the same post
    shared different ways maps to one database row.
    """
    if not isinstance(url, str):
        return None
    url = url.strip()
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None

    if parts.scheme.lower() != "https" or host not in INSTAGRAM_HOSTS:
        return None
    if parts.username or parts.password or port not in (None, 443):
        return None

    match = _POST_PATH.match(parts.path)
    if not match:
        return None
    kind = "reel" if match["kind"] == "reels" else match["kind"]
    return f"https://www.instagram.com/{kind}/{match['code']}/"


def validate_instagram_url(url: str) -> bool:
    """Whether `url` looks like an Instagram post URL.

    This only checks the format. Whether the post can actually be retrieved is
    decided by the Instagram integration.
    """
    return normalize_instagram_url(url) is not None


@dataclass(frozen=True)
class CreatePostResult:
    post: Post
    created: bool  # False when the URL had already been added


@wrap_db_errors
def _find_by_url(instagram_url: str) -> Post | None:
    with get_session() as session:
        return session.scalar(select(Post).where(Post.instagram_url == instagram_url))


@wrap_db_errors
def _insert_post(media: InstagramPost) -> Post | None:
    """Insert and return the post, or None if another request inserted it first."""
    try:
        with get_session() as session:
            post = Post(
                instagram_url=media.instagram_url,
                media_url=media.media_url,
                caption=media.caption,
                embed_html=media.embed_html,
            )
            session.add(post)
            session.flush()
            session.refresh(post)
            return post
    except IntegrityError:
        return None


def create_post(instagram_url: str, client: InstagramClient | None = None) -> CreatePostResult:
    """Validate, de-duplicate, resolve through Instagram, then persist a post.

    Raises InvalidInstagramURLError, an InstagramError subclass when Instagram
    won't provide the post (nothing is saved in that case), or DatabaseError.
    """
    normalized = normalize_instagram_url(instagram_url)
    if normalized is None:
        raise InvalidInstagramURLError()

    existing = _find_by_url(normalized)
    if existing is not None:
        return CreatePostResult(post=existing, created=False)

    client = client or get_instagram_client()
    media = client.get_post(normalized)
    media = media.model_copy(update={"instagram_url": normalized})

    post = _insert_post(media)
    if post is None:
        return CreatePostResult(post=_find_by_url(normalized), created=False)
    return CreatePostResult(post=post, created=True)


@wrap_db_errors
def get_post(post_id: int) -> Post | None:
    with get_session() as session:
        return session.get(Post, post_id)


@wrap_db_errors
def list_posts() -> list[Post]:
    """All posts, newest first."""
    with get_session() as session:
        return list(session.scalars(select(Post).order_by(Post.created_at.desc(), Post.id.desc())))
