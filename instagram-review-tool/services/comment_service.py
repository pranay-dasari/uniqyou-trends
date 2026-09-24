"""Anonymous comments on posts."""

from __future__ import annotations

from sqlalchemy import func, select

from database.db import get_session
from database.models import Comment, Post
from services.errors import EmptyCommentError, PostNotFoundError, wrap_db_errors

MAX_COMMENT_LENGTH = 2000


@wrap_db_errors
def add_comment(post_id: int, comment_text: str) -> Comment:
    text = (comment_text or "").strip()
    if not text:
        raise EmptyCommentError()
    text = text[:MAX_COMMENT_LENGTH]

    with get_session() as session:
        if session.get(Post, post_id) is None:
            raise PostNotFoundError()
        comment = Comment(post_id=post_id, comment_text=text)
        session.add(comment)
        session.flush()
        session.refresh(comment)
        return comment


@wrap_db_errors
def get_comments(post_id: int) -> list[Comment]:
    """Comments for a post, oldest first."""
    with get_session() as session:
        return list(
            session.scalars(
                select(Comment)
                .where(Comment.post_id == post_id)
                .order_by(Comment.created_at, Comment.id)
            )
        )


@wrap_db_errors
def get_comment_count(post_id: int) -> int:
    with get_session() as session:
        return session.scalar(
            select(func.count()).select_from(Comment).where(Comment.post_id == post_id)
        )
