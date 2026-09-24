"""Errors raised by the service layer. `user_message` is safe to display."""

from __future__ import annotations

import functools
import logging

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class ServiceError(Exception):
    user_message = "Something went wrong. Please try again."


class InvalidInstagramURLError(ServiceError):
    user_message = "Please enter a valid Instagram post URL."


class EmptyCommentError(ServiceError):
    user_message = "Comment cannot be empty."


class PostNotFoundError(ServiceError):
    user_message = "That post no longer exists."


class DatabaseError(ServiceError):
    user_message = "A database error occurred. Please try again."


def wrap_db_errors(func):
    """Log SQLAlchemy failures server-side and re-raise a generic DatabaseError."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError:
            logger.exception("Database error in %s", func.__name__)
            raise DatabaseError() from None

    return wrapper
