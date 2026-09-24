"""Post cards, upvotes, comments and the post-detail dialog."""

from __future__ import annotations

import html
import logging

import streamlit as st

from database.models import Post
from services.comment_service import (
    MAX_COMMENT_LENGTH,
    add_comment,
    get_comment_count,
    get_comments,
)
from services.errors import ServiceError
from services.post_service import get_post
from services.vote_service import add_upvote, get_upvote_count

logger = logging.getLogger(__name__)

EMBED_HEIGHT = 720

# Instagram's standard embed markup, filled with our own validated, canonical
# post URL. We don't render the HTML stored from the API: st.iframe runs HTML
# strings with scripts *and* same-origin access, so anything in that HTML would
# run with the app's privileges.
_EMBED_TEMPLATE = (
    '<blockquote class="instagram-media" data-instgrm-permalink="{url}" '
    'data-instgrm-version="14" style="margin:0 auto;max-width:540px;width:100%;">'
    '<a href="{url}" target="_blank" rel="noopener">View this post on Instagram</a>'
    "</blockquote>"
    '<script async src="https://www.instagram.com/embed.js"></script>'
)


# ---------------------------------------------------------------- media


def render_media(post: Post, height: int = EMBED_HEIGHT, image_width: int | str = "stretch") -> None:
    if post.media_url:
        st.image(post.media_url, width=image_width)
    elif post.embed_html:
        # oEmbed confirmed the post is public and embeddable; show Instagram's embed.
        embed = _EMBED_TEMPLATE.format(url=html.escape(post.instagram_url, quote=True))
        st.iframe(embed, height=height)
    else:
        st.info("Instagram did not provide an image for this post.")


# ---------------------------------------------------------------- upvotes


def _on_upvote(post_id: int, error_key: str) -> None:
    try:
        add_upvote(post_id)
    except ServiceError as exc:
        st.session_state[error_key] = exc.user_message


def render_upvote(post: Post, key_prefix: str) -> None:
    error_key = f"{key_prefix}_upvote_error_{post.id}"
    count = _safe(get_upvote_count, post.id, default=0)
    st.button(
        f"Upvote · {count}",
        icon=":material/thumb_up:",
        type="primary",
        key=f"{key_prefix}_upvote_{post.id}",
        on_click=_on_upvote,
        args=(post.id, error_key),
    )
    if message := st.session_state.pop(error_key, None):
        st.error(message)


# ---------------------------------------------------------------- comments


def _on_comment(post_id: int, input_key: str, error_key: str) -> None:
    try:
        add_comment(post_id, st.session_state.get(input_key, ""))
    except ServiceError as exc:
        st.session_state[error_key] = exc.user_message


def render_comments(post: Post, key_prefix: str) -> None:
    input_key = f"{key_prefix}_comment_input_{post.id}"
    error_key = f"{key_prefix}_comment_error_{post.id}"

    comments = _safe(get_comments, post.id, default=[])
    st.html(f'<p class="comments-title">Comments · {len(comments)}</p>')
    if comments:
        st.html(
            "".join(
                f'<div class="comment">{_plain_text(c.comment_text)}'
                f"<small>{c.created_at:%Y-%m-%d %H:%M} UTC</small></div>"
                for c in comments
            )
        )
    else:
        st.caption("No comments yet.")

    with st.form(f"{key_prefix}_comment_form_{post.id}", clear_on_submit=True, border=False):
        st.text_input(
            "Comment",
            placeholder="Write a comment…",
            key=input_key,
            max_chars=MAX_COMMENT_LENGTH,
            label_visibility="collapsed",
        )
        st.form_submit_button(
            "Add comment", width="stretch", on_click=_on_comment, args=(post.id, input_key, error_key)
        )
    if message := st.session_state.pop(error_key, None):
        st.error(message)


# ---------------------------------------------------------------- composites


@st.dialog("Post details", width="large", on_dismiss="rerun")
def open_post_dialog(post_id: int, status: str = "Saved post") -> None:
    # Re-read inside the dialog so interactions (which rerun only the dialog)
    # always show current data. Closing it reruns the page to refresh counts.
    post = _safe(get_post, post_id, default=None)
    if post is None:
        st.error("That post no longer exists.")
        return
    st.html(f'<div class="status-strip">{html.escape(status)}</div>')
    media_col, side_col = st.columns([1, 1], gap="medium")
    with media_col:
        render_media(post, height=640)
    with side_col:
        upvote_col, link_col = st.columns(2)
        with upvote_col:
            render_upvote(post, key_prefix="dialog")
        with link_col:
            st.link_button("Instagram", post.instagram_url, icon=":material/open_in_new:", width="stretch")
        render_comments(post, key_prefix="dialog")


def render_post_card(post: Post, key_prefix: str) -> None:
    """Grid card: media, upvote, and a button that opens the popup."""
    with st.container(border=True, key=f"card_{post.id}"):
        render_media(post, height=420)
        upvote_col, open_col = st.columns(2)
        with upvote_col:
            render_upvote(post, key_prefix)
        with open_col:
            comment_count = _safe(get_comment_count, post.id, default=0)
            if st.button(
                f"{comment_count} · Open",
                icon=":material/chat_bubble:",
                key=f"{key_prefix}_open_{post.id}",
                width="stretch",
            ):
                open_post_dialog(post.id)


def _plain_text(text: str) -> str:
    """User text shown exactly as typed: no markdown, links or HTML."""
    return f'<p style="margin:0;white-space:pre-wrap;overflow-wrap:anywhere">{html.escape(text)}</p>'


def _safe(func, *args, default):
    """Call a read service; show the generic message instead of crashing the page."""
    try:
        return func(*args)
    except ServiceError as exc:
        st.error(exc.user_message)
        return default
