"""Upvotes. In V1 an upvote is an anonymous +1 for a post."""

from __future__ import annotations

from sqlalchemy import func, select

from database.db import get_session
from database.models import Post, Upvote
from services.errors import PostNotFoundError, wrap_db_errors


@wrap_db_errors
def add_upvote(post_id: int) -> int:
    """Record one upvote and return the post's new total."""
    with get_session() as session:
        if session.get(Post, post_id) is None:
            raise PostNotFoundError()
        session.add(Upvote(post_id=post_id))
        session.flush()
        return _count(session, post_id)


@wrap_db_errors
def get_upvote_count(post_id: int) -> int:
    with get_session() as session:
        return _count(session, post_id)


def _count(session, post_id: int) -> int:
    return session.scalar(select(func.count()).select_from(Upvote).where(Upvote.post_id == post_id))
